from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ImpactReportFilters:
    channel: str | None = None
    action_statuses: tuple[str, ...] = ()
    currency: str | None = None

    @classmethod
    def from_env(cls) -> ImpactReportFilters:
        channel = os.getenv("IMPACT_REPORT_CHANNEL", "").strip() or None
        statuses_raw = os.getenv("IMPACT_REPORT_ACTION_STATUS", "").strip()
        action_statuses = (
            tuple(s.strip() for s in statuses_raw.split(",") if s.strip())
            if statuses_raw
            else ()
        )
        currency = os.getenv("IMPACT_REPORT_CURRENCY", "").strip() or None
        return cls(channel=channel, action_statuses=action_statuses, currency=currency)

    def to_api_params(self) -> dict[str, str]:
        """Params sent to ReportExport, plus local post-filtering in apply_filters_to_csv."""
        params: dict[str, str] = {}
        if self.channel:
            params["Channel"] = self.channel
        if self.currency:
            params["CONV_CURRENCY"] = self.currency
        if self.action_statuses:
            params["ACTION_STATUS"] = ",".join(self.action_statuses)
        return params

    @property
    def enabled(self) -> bool:
        return bool(self.channel or self.action_statuses or self.currency)


def apply_filters_to_csv(csv_bytes: bytes, filters: ImpactReportFilters) -> bytes:
    if not filters.enabled:
        return csv_bytes

    text = csv_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return csv_bytes

    allowed_statuses = {_normalize(s) for s in filters.action_statuses}
    allowed_channel = _normalize(filters.channel) if filters.channel else None
    allowed_currency = (filters.currency or "").upper()

    kept: list[dict[str, str]] = []
    for row in reader:
        if allowed_statuses:
            status = _normalize(row.get("Status") or row.get("State") or "")
            if status not in allowed_statuses:
                continue

        if allowed_channel:
            channel = _normalize(row.get("Channel") or "")
            if channel and channel != allowed_channel:
                continue

        if allowed_currency:
            currency = (row.get("Original_Currency") or row.get("Currency") or "").upper()
            if currency and currency != allowed_currency:
                continue

        kept.append(row)

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=reader.fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(kept)
    return out.getvalue().encode("utf-8")


def _normalize(value: str) -> str:
    return " ".join(value.strip().lower().split())
