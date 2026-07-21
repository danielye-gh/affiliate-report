from __future__ import annotations

from typing import Any

from affiliate_report.models import MonthRange
from affiliate_report.platforms.impact.client import ImpactClient, ImpactAPIError


class ImpactReportsAPI:
    """Impact Reports + ReportExport — for monthly Advanced Action Listing exports."""

    def __init__(self, client: ImpactClient):
        self._client = client

    def list_reports(self) -> list[dict[str, Any]]:
        payload = self._client.get_json(self._client._path("/Reports"))
        return payload.get("Reports") or []

    def list_api_accessible_reports(self) -> list[dict[str, Any]]:
        return [r for r in self.list_reports() if r.get("ApiAccessible")]

    def get_report_metadata(self, report_handle: str) -> dict[str, Any]:
        return self._client.get_json(
            self._client._path(f"/Reports/{report_handle}/MetaData")
        )

    def export_report_csv(
        self,
        report_handle: str,
        month: MonthRange,
        *,
        program_id: str | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> bytes:
        """Schedule async export, poll job, return CSV bytes."""
        params = self._build_date_params(month)
        if program_id:
            params["SUBAID"] = program_id
        if extra_params:
            params.update(extra_params)
        params["ResultFormat"] = "CSV"

        export_path = self._client._path(f"/ReportExport/{report_handle}")
        queued = self._client.get_json(export_path, params=params)

        status = queued.get("Status", "")
        if status and status not in {"QUEUED", "OK"}:
            raise ImpactAPIError(f"Unexpected export queue status: {status}", body=queued)

        queued_uri = queued.get("QueuedUri")
        if not queued_uri:
            # Some responses may already include downloadable ResultUri
            result_uri = queued.get("ResultUri")
            if result_uri:
                return self._client.download(_normalize(result_uri))
            raise ImpactAPIError("ReportExport response missing QueuedUri", body=queued)

        job = self._client.poll_job_until_complete(queued_uri)
        return self._client.download_job_result(job)

    def run_report_sync(
        self,
        report_handle: str,
        month: MonthRange,
        *,
        program_id: str | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Legacy sync report — max ~20k rows. Same data as UI Advanced Action Listing."""
        params = self._build_sync_date_params(month)
        if program_id:
            params["SUBAID"] = program_id
        if extra_params:
            params.update(extra_params)
        payload = self._client.get_json(
            self._client._path(f"/Reports/{report_handle}"),
            params=params,
        )
        return payload.get("Records") or []

    def run_report_sync_csv(
        self,
        report_handle: str,
        month: MonthRange,
        *,
        program_id: str | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> bytes:
        records = self.run_report_sync(
            report_handle, month, program_id=program_id, extra_params=extra_params
        )
        if not records:
            return b""
        fieldnames = sorted({key for row in records for key in row})
        import io
        import csv

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
        return buffer.getvalue().encode("utf-8")

    def _build_date_params(self, month: MonthRange) -> dict[str, str]:
        # ReportExport uses START_DATE/END_DATE for both advertiser and partner accounts.
        return {"START_DATE": month.start_iso, "END_DATE": month.end_iso}

    def _build_sync_date_params(self, month: MonthRange) -> dict[str, str]:
        if self._client.account_type == "advertiser":
            return {"StartDate": month.start_iso, "EndDate": month.end_iso}
        return {"START_DATE": month.start_iso, "END_DATE": month.end_iso}


def _normalize(uri: str) -> str:
    if uri.startswith("http"):
        from urllib.parse import urlparse

        return urlparse(uri).path
    return uri if uri.startswith("/") else f"/{uri}"
