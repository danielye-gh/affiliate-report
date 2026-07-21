from __future__ import annotations

import sys
from typing import Any

import httpx

AWIN_BASE_URL = "https://api.awin.com"


class AwinAPIError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class AwinClient:
    """Low-level HTTP client for Awin REST API."""

    def __init__(
        self,
        api_token: str,
        *,
        base_url: str = AWIN_BASE_URL,
        timeout: float = 120.0,
        verbose: bool = False,
    ):
        self.verbose = verbose
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_token}",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> AwinClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _log_request(self, method: str, url: str | httpx.URL, *, params: dict[str, Any] | None = None) -> None:
        if params:
            request = self._client.build_request(method, str(url), params=params)
            print(f">>> {method} {request.url}", file=sys.stderr, flush=True)
        else:
            print(f">>> {method} {url}", file=sys.stderr, flush=True)

    def _log_response(self, response: httpx.Response) -> None:
        if not self.verbose:
            return
        print(
            f"<<< {response.status_code} {response.request.method} {response.request.url}",
            file=sys.stderr,
            flush=True,
        )

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> httpx.Response:
        self._log_request("GET", path, params=params)
        response = self._client.get(path, params=params)
        self._log_response(response)
        if response.status_code >= 400:
            raise AwinAPIError(
                f"Awin API GET {path} failed: {response.status_code}",
                status_code=response.status_code,
                body=_safe_json(response),
            )
        return response

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self.get(path, params=params).json()


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text[:500]
