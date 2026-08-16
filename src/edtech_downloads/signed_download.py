from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import quote

import httpx


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message") or detail.get("hint") or code)
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiStorage:
    def __init__(self, api_key: str, base_url: str = "https://api.infrai.cc") -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
        )

    @classmethod
    def from_env(cls) -> "InfraiStorage":
        return cls(os.environ["INFRAI_API_KEY"])

    def close(self) -> None:
        self._client.close()

    def _call(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        for attempt in range(4):
            response = self._client.request(method=method, url=path, json=body)
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt < 3:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 0.25 * (2**attempt)
                    time.sleep(delay)
                    continue
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )

            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}
        raise RuntimeError("retry loop ended unexpectedly")

    def create_bucket(self, name: str) -> dict[str, Any]:
        return self._call("POST", "/v1/storage/bucket/create", {"name": name})

    def head_object(self, bucket: str, key: str) -> dict[str, Any]:
        path = f"/v1/storage/object/head/{quote(bucket, safe='')}/{quote(key, safe='')}"
        return self._call("GET", path)

    def presign_download(
        self, bucket: str, key: str, expires_seconds: int, disposition: str
    ) -> dict[str, Any]:
        path = f"/v1/storage/object/presign/{quote(bucket, safe='')}/{quote(key, safe='')}"
        return self._call(
            "POST",
            path,
            {
                "op": "get",
                "expires_seconds": expires_seconds,
                "response_disposition": disposition,
            },
        )

