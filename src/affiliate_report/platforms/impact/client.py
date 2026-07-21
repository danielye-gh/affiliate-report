from __future__ import annotations

import sys
import time
from typing import Any

import httpx

IMPACT_BASE_URL = "https://api.impact.com"
DEFAULT_POLL_INTERVAL = 5
DEFAULT_MAX_WAIT = 600


class ImpactAPIError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class ImpactClient:
    """Low-level HTTP client for Impact.com REST API."""

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        *,
        account_type: str = "advertiser",
        base_url: str = IMPACT_BASE_URL,
        timeout: float = 120.0,
        verbose: bool = False,
    ):
        self.account_sid = account_sid
        self.account_type = account_type
        self.verbose = verbose
        self._prefix = "Advertisers" if account_type == "advertiser" else "Mediapartners"
        self._client = httpx.Client(
            base_url=base_url,
            auth=(account_sid, auth_token),
            timeout=timeout,
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ImpactClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _path(self, suffix: str) -> str:
        return f"/{self._prefix}/{self.account_sid}{suffix}"

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
            raise ImpactAPIError(
                f"Impact API GET {path} failed: {response.status_code}",
                status_code=response.status_code,
                body=_safe_json(response),
            )
        return response

    def get_absolute(self, url: str) -> httpx.Response:
        self._log_request("GET", url)
        response = self._client.get(url)
        self._log_response(response)
        if response.status_code >= 400:
            raise ImpactAPIError(
                f"Impact API GET {url} failed: {response.status_code}",
                status_code=response.status_code,
                body=_safe_json(response),
            )
        return response

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.get(path, params=params).json()

    def download(self, path: str) -> bytes:
        response = self.get(path)
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = response.json()
            if isinstance(payload, dict) and payload.get("Status") in {
                "QUEUED",
                "RUNNING",
            }:
                raise ImpactAPIError("Job not complete yet", body=payload)
        return response.content

    def poll_job_until_complete(
        self,
        queued_uri: str,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_wait: float = DEFAULT_MAX_WAIT,
    ) -> dict[str, Any]:
        """Poll QueuedUri until job completes; return final job object."""
        deadline = time.monotonic() + max_wait
        job_path = _normalize_api_path(queued_uri)
        if not job_path.endswith(".json"):
            job_path = f"{job_path}.json"

        while time.monotonic() < deadline:
            try:
                job = self.get_json(job_path)
            except ImpactAPIError as exc:
                if exc.status_code == 403:
                    raise ImpactAPIError(
                        "Jobs API returned 403. Enable the Jobs (read) scope on your "
                        "Impact API token, or use --method actions instead.",
                        status_code=403,
                        body=exc.body,
                    ) from exc
                raise
            status = job.get("Status", "")
            if status == "COMPLETED":
                return job
            if status in {"ERROR", "FAILED", "CANCELLED"}:
                raise ImpactAPIError(
                    f"Impact job failed with status {status}: {job.get('StatusMessage')}",
                    body=job,
                )
            print(
                f"... Impact job {status!r}, checking again in {int(poll_interval)}s",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(poll_interval)

        raise ImpactAPIError(f"Timed out waiting for Impact job at {job_path}")

    def download_job_result(self, job: dict[str, Any]) -> bytes:
        result_uri = job.get("ResultUri")
        if not result_uri:
            raise ImpactAPIError("Job completed but ResultUri is missing", body=job)

        job_id = _extract_job_id(result_uri)
        download_path = _normalize_api_path(f"{self._path(f'/Jobs/{job_id}/Download')}")

        deadline = time.monotonic() + DEFAULT_MAX_WAIT
        while time.monotonic() < deadline:
            self._log_request("GET", download_path)
            response = self._client.get(download_path)
            self._log_response(response)

            if response.status_code == 302:
                signed_url = response.headers.get("location")
                if not signed_url:
                    raise ImpactAPIError("Download redirect missing location header")
                file_response = self.get_absolute(signed_url)
                return file_response.content

            if response.status_code == 202:
                payload = _safe_json(response)
                status = payload.get("Status", "") if isinstance(payload, dict) else ""
                if status == "COMPLETED":
                    continue
                print(
                    f"... Impact download {status!r}, retry in {int(DEFAULT_POLL_INTERVAL)}s",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(DEFAULT_POLL_INTERVAL)
                continue

            if response.status_code == 403:
                raise ImpactAPIError(
                    "Jobs Download returned 403. Enable the Jobs (read) scope on your "
                    "Impact API token, or use --method actions instead.",
                    status_code=403,
                    body=_safe_json(response),
                )

            if response.status_code >= 400:
                raise ImpactAPIError(
                    f"Failed to download job result: {response.status_code}",
                    status_code=response.status_code,
                    body=_safe_json(response),
                )

            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                payload = response.json()
                if isinstance(payload, dict) and payload.get("Status") in {"QUEUED", "RUNNING"}:
                    print(
                        f"... Impact download {payload.get('Status')!r}, retry in {int(DEFAULT_POLL_INTERVAL)}s",
                        file=sys.stderr,
                        flush=True,
                    )
                    time.sleep(DEFAULT_POLL_INTERVAL)
                    continue

            return response.content

        raise ImpactAPIError(f"Timed out downloading job result for {job_id}")


def _normalize_api_path(uri: str) -> str:
    if uri.startswith("http"):
        from urllib.parse import urlparse

        parsed = urlparse(uri)
        return parsed.path
    return uri if uri.startswith("/") else f"/{uri}"


def _extract_job_id(result_uri: str) -> str:
    path = _normalize_api_path(result_uri)
    parts = [p for p in path.split("/") if p]
    if "Jobs" in parts:
        idx = parts.index("Jobs")
        return parts[idx + 1]
    raise ImpactAPIError(f"Cannot parse Job ID from ResultUri: {result_uri}")


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text[:500]
