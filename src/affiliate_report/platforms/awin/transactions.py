from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from affiliate_report.models import MonthRange
from affiliate_report.platforms.awin.client import AwinClient
from affiliate_report.platforms.awin.config import AwinSiteConfig

# Awin limits transaction list queries to 31 calendar days per request.
MAX_RANGE_DAYS = 31


class AwinTransactionsAPI:
    def __init__(self, client: AwinClient):
        self._client = client

    def list_transactions_for_month(
        self,
        site: AwinSiteConfig,
        month: MonthRange,
        *,
        date_type: str = "transaction",
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for start, end in _month_date_chunks(month):
            chunk = self._list_transactions(
                site,
                start,
                end,
                date_type=date_type,
                status=status,
            )
            rows.extend(chunk)
        return rows

    def _list_transactions(
        self,
        site: AwinSiteConfig,
        start: date,
        end: date,
        *,
        date_type: str,
        status: str | None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "startDate": f"{start.isoformat()}T00:00:00",
            "endDate": f"{end.isoformat()}T23:59:59",
            "timezone": site.timezone,
            "dateType": date_type,
        }
        if status:
            params["status"] = status

        path = f"/advertisers/{site.advertiser_id}/transactions/"
        payload = self._client.get_json(path, params=params)
        if not isinstance(payload, list):
            raise ValueError(f"Unexpected Awin transactions response for {site.label}: {payload!r}")
        return payload


def _month_date_chunks(month: MonthRange) -> list[tuple[date, date]]:
    """Split a month into <=31-day chunks for Awin API limits."""
    start = month.start
    end = month.end
    if (end - start).days + 1 <= MAX_RANGE_DAYS:
        return [(start, end)]

    chunks: list[tuple[date, date]] = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=MAX_RANGE_DAYS - 1), end)
        chunks.append((chunk_start, chunk_end))
        chunk_start = chunk_end + timedelta(days=1)
    return chunks
