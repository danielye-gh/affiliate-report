from __future__ import annotations

import json
import sys
from typing import Any

import httpx

CJ_COMMISSIONS_URL = "https://commissions.api.cj.com/query"


class CJAPIError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class CJClient:
    """Low-level HTTP client for CJ GraphQL Commission Detail API."""

    def __init__(
        self,
        api_token: str,
        *,
        base_url: str = CJ_COMMISSIONS_URL,
        timeout: float = 120.0,
        verbose: bool = False,
    ):
        self.verbose = verbose
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_token}",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CJClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def graphql(self, query: str, *, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": _compact_query(query)}
        if variables:
            payload["variables"] = variables

        if self.verbose:
            print(f">>> POST {self._client.base_url}", file=sys.stderr, flush=True)
            print(f"    query: {payload['query'][:200]}...", file=sys.stderr, flush=True)
        else:
            print(f">>> POST {self._client.base_url}", file=sys.stderr, flush=True)

        response = self._client.post("", json=payload)
        if self.verbose:
            print(f"<<< {response.status_code} POST {response.request.url}", file=sys.stderr, flush=True)

        body = _safe_json(response)
        if response.status_code >= 400:
            raise CJAPIError(
                f"CJ GraphQL request failed: {response.status_code}",
                status_code=response.status_code,
                body=body,
            )

        if isinstance(body, dict) and body.get("errors"):
            message = "; ".join(
                str(err.get("message", err)) for err in body["errors"] if isinstance(err, dict)
            )
            raise CJAPIError(message or "CJ GraphQL returned errors", body=body)

        if not isinstance(body, dict) or "data" not in body:
            raise CJAPIError("Unexpected CJ GraphQL response", body=body)

        return body["data"]


def _compact_query(query: str) -> str:
    return " ".join(line.strip() for line in query.strip().splitlines() if line.strip())


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text[:500]
