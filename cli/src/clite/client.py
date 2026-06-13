"""HTTP-клиент для tasks-svc."""

from __future__ import annotations

import sys
from typing import Any

import httpx

from clite.config import Config


class APIError(Exception):
    def __init__(self, status_code: int, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class Client:
    def __init__(self, config: Config) -> None:
        self.config = config
        headers: dict[str, str] = {"User-Agent": "clite/0.1.0"}
        if config.token:
            headers["Authorization"] = f"Bearer {config.token}"
        self._client = httpx.Client(
            base_url=f"{config.base_url}/api",
            headers=headers,
            timeout=httpx.Timeout(30.0, connect=5.0),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def request(self, method: str, path: str, **kwargs: object) -> dict[str, Any] | list[Any]:
        try:
            response = self._client.request(method, path, **kwargs)  # type: ignore[arg-type]
        except httpx.HTTPError as e:
            print(f"connection failed: {e}", file=sys.stderr)
            raise SystemExit(1) from e

        if response.status_code == 401:
            raise APIError(401, "not authenticated, run `clite login`")
        if response.status_code == 403:
            detail = _extract_detail(response)
            raise APIError(403, f"forbidden: {detail or 'access denied'}", detail)
        if response.status_code == 404:
            raise APIError(404, "not found", _extract_detail(response))
        if response.status_code == 400:
            raise APIError(400, _extract_detail(response) or "bad request")
        if response.status_code >= 500:
            request_id = response.headers.get("x-request-id", "")
            raise APIError(
                response.status_code,
                f"server error {response.status_code} (request-id: {request_id})",
            )
        try:
            return response.json()  # type: ignore[no-any-return]
        except ValueError as e:
            raise APIError(response.status_code, f"invalid JSON response: {e}") from e

    def get(self, path: str, params: dict[str, object] | None = None) -> dict[str, Any] | list[Any]:
        return self.request("GET", path, params=params)

    def post(
        self,
        path: str,
        json: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, Any] | list[Any]:
        return self.request("POST", path, json=json, params=params)

    def patch(self, path: str, json: dict[str, object] | None = None) -> dict[str, Any] | list[Any]:
        return self.request("PATCH", path, json=json)


def _extract_detail(response: httpx.Response) -> str | None:
    try:
        data = response.json()
    except ValueError:
        return None
    if isinstance(data, dict):
        detail = data.get("detail")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, list) and detail:
            first = detail[0]
            if isinstance(first, dict) and "msg" in first:
                return str(first["msg"])
        if "error" in data and isinstance(data["error"], str):
            return data["error"]
    return None
