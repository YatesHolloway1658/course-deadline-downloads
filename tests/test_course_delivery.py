from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.testclient import TestClient

from edtech_downloads.course_delivery import create_app


class RecordingStorage:
    def __init__(self, found: bool = True) -> None:
        self.found = found
        self.presign_ttls: list[int] = []

    def create_bucket(self, name: str) -> dict[str, Any]:
        return {"name": name}

    def head_object(self, bucket: str, key: str) -> dict[str, Any]:
        return {"found": self.found}

    def presign_download(
        self, bucket: str, key: str, expires_seconds: int, disposition: str
    ) -> dict[str, Any]:
        self.presign_ttls.append(expires_seconds)
        return {"url": "https://downloads.example/signed-course-file"}


def test_link_is_shortened_to_the_learner_deadline_and_reported() -> None:
    storage = RecordingStorage()
    app = create_app(storage=storage, bucket="course-materials")

    with TestClient(app) as client:
        deadline = datetime.now(timezone.utc) + timedelta(seconds=121)
        response = client.post(
            "/downloads",
            json={
                "course_id": "python-101",
                "learner_id": "learner-7",
                "material_key": "python-101/week-2.pdf",
                "deadline": deadline.isoformat(),
            },
        )
        report = client.get("/courses/python-101/delivery-report")

    assert response.status_code == 200
    assert 119 <= storage.presign_ttls[0] <= 120
    assert report.json()["links_issued"] == 1
    assert report.json()["deliveries"][0]["learner_id"] == "learner-7"


def test_expired_deadline_does_not_issue_a_link() -> None:
    storage = RecordingStorage()
    app = create_app(storage=storage, bucket="course-materials")

    with TestClient(app) as client:
        response = client.post(
            "/downloads",
            json={
                "course_id": "python-101",
                "learner_id": "learner-7",
                "material_key": "python-101/week-2.pdf",
                "deadline": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            },
        )

    assert response.status_code == 409
    assert storage.presign_ttls == []

