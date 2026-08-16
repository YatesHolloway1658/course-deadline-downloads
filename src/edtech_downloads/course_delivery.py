from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Iterator

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .signed_download import InfraiError, InfraiStorage


class DownloadRequest(BaseModel):
    course_id: str = Field(min_length=1)
    learner_id: str = Field(min_length=1)
    material_key: str = Field(min_length=1)
    deadline: datetime


class DownloadGrant(BaseModel):
    course_id: str
    learner_id: str
    material_key: str
    download_url: str
    expires_at: datetime


class DeliveryRecord(BaseModel):
    learner_id: str
    material_key: str
    issued_at: datetime
    expires_at: datetime


class CourseReport(BaseModel):
    course_id: str
    links_issued: int
    deliveries: list[DeliveryRecord]


class DeliveryLedger:
    def __init__(self) -> None:
        self._records: dict[str, list[DeliveryRecord]] = {}
        self._lock = Lock()

    def add(self, course_id: str, record: DeliveryRecord) -> None:
        with self._lock:
            self._records.setdefault(course_id, []).append(record)

    def report(self, course_id: str) -> CourseReport:
        with self._lock:
            records = list(self._records.get(course_id, []))
        return CourseReport(
            course_id=course_id, links_issued=len(records), deliveries=records
        )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise HTTPException(status_code=422, detail="deadline must include a timezone")
    return value.astimezone(timezone.utc)


def create_app(
    storage: Any | None = None,
    bucket: str | None = None,
    ledger: DeliveryLedger | None = None,
) -> FastAPI:
    selected_bucket = bucket or os.environ.get("COURSE_FILES_BUCKET", "course-materials")
    selected_storage = storage
    selected_ledger = ledger or DeliveryLedger()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Iterator[None]:
        nonlocal selected_storage
        if selected_storage is None:
            selected_storage = InfraiStorage.from_env()
        selected_storage.create_bucket(selected_bucket)
        yield
        if isinstance(selected_storage, InfraiStorage):
            selected_storage.close()

    app = FastAPI(title="Private course delivery", lifespan=lifespan)

    @app.exception_handler(InfraiError)
    async def infrai_error_handler(_, exc: InfraiError):
        from fastapi.responses import JSONResponse

        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        return JSONResponse(
            status_code=status,
            content={"detail": {"code": exc.code, "message": str(exc)}},
        )

    @app.post("/downloads", response_model=DownloadGrant)
    def issue_download(request: DownloadRequest) -> DownloadGrant:
        assert selected_storage is not None
        now = datetime.now(timezone.utc)
        deadline = _utc(request.deadline)
        seconds_left = int((deadline - now).total_seconds())
        if seconds_left <= 0:
            raise HTTPException(status_code=409, detail="course deadline has passed")

        object_state = selected_storage.head_object(selected_bucket, request.material_key)
        if not object_state.get("found"):
            raise HTTPException(status_code=404, detail="course material was not found")

        ttl = min(900, seconds_left)
        signed = selected_storage.presign_download(
            selected_bucket,
            request.material_key,
            ttl,
            f'attachment; filename="{request.material_key.rsplit("/", 1)[-1]}"',
        )
        expires_at = now.replace(microsecond=0) + timedelta(seconds=ttl)
        grant = DownloadGrant(
            course_id=request.course_id,
            learner_id=request.learner_id,
            material_key=request.material_key,
            download_url=str(signed["url"]),
            expires_at=expires_at,
        )
        selected_ledger.add(
            request.course_id,
            DeliveryRecord(
                learner_id=request.learner_id,
                material_key=request.material_key,
                issued_at=now,
                expires_at=expires_at,
            ),
        )
        return grant

    @app.get("/courses/{course_id}/delivery-report", response_model=CourseReport)
    def delivery_report(course_id: str) -> CourseReport:
        return selected_ledger.report(course_id)

    return app


app = create_app()
