from __future__ import annotations

import csv
import io
from typing import Any

from affiliate_report.impact_filters import ImpactReportFilters, _normalize
from affiliate_report.models import MonthRange
from affiliate_report.platforms.impact.actions import ImpactActionsAPI
from affiliate_report.platforms.impact.client import ImpactClient

ACTION_STATUS_API_STATE = {
    "approved": "APPROVED",
    "pending": "PENDING",
    "reversed": "REVERSED",
}


def supplement_csv_with_missing_action_statuses(
    csv_bytes: bytes,
    filters: ImpactReportFilters,
    *,
    http: ImpactClient,
    month: MonthRange,
    program_id: str | None,
) -> bytes:
    """Add Actions API rows for requested statuses missing from report export."""
    if not filters.action_statuses or not program_id:
        return csv_bytes

    text = csv_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames
    if not fieldnames:
        return csv_bytes

    rows = list(reader)
    present_statuses = {
        _normalize(row.get("Status") or row.get("State") or "")
        for row in rows
        if _normalize(row.get("Status") or row.get("State") or "")
    }
    requested_statuses = {_normalize(status) for status in filters.action_statuses}
    missing_statuses = requested_statuses - present_statuses
    if not missing_statuses:
        return csv_bytes

    actions_api = ImpactActionsAPI(http)
    seen_action_ids = {
        str(row.get("Action_Id") or row.get("Action Id") or row.get("Id") or "").strip()
        for row in rows
        if str(row.get("Action_Id") or row.get("Action Id") or row.get("Id") or "").strip()
    }

    for status in sorted(missing_statuses):
        api_state = ACTION_STATUS_API_STATE.get(status)
        if not api_state:
            continue
        actions = actions_api.list_actions_for_advertiser_month(
            month,
            campaign_ids=[program_id],
            state=api_state,
        )
        for action in actions:
            action_id = str(action.get("Id") or "").strip()
            if not action_id or action_id in seen_action_ids:
                continue
            rows.append(_action_to_report_row(action, fieldnames))
            seen_action_ids.add(action_id)

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def _action_to_report_row(action: dict[str, Any], fieldnames: list[str]) -> dict[str, str]:
    amount = _stringify(action.get("Amount"))
    payout = _stringify(action.get("Payout"))
    rate = ""
    if amount and payout:
        try:
            sale = float(amount)
            pay = float(payout)
            if sale:
                rate = f"{pay / sale:.4f}".rstrip("0").rstrip(".")
        except ValueError:
            rate = ""

    mapped = {
        "Action_Date": _stringify(action.get("EventDate")),
        "Action_Id": _stringify(action.get("Id")),
        "OID": _stringify(action.get("Oid")),
        "Status": _stringify(action.get("State")),
        "Sale_Amount": amount,
        "Payout": payout,
        "Rate": rate,
        "Promo_Code": _stringify(action.get("PromoCode")),
        "Media_Partner": _stringify(action.get("MediaPartnerName")),
        "mp_id": _stringify(action.get("MediaPartnerId")),
        "Action_Tracker": _stringify(action.get("ActionTrackerName")),
        "AT_Id": _stringify(action.get("ActionTrackerId")),
        "Referring_URL": _stringify(action.get("ReferringDomain")),
        "Shared_Id": _stringify(action.get("SharedId")),
        "Currency": _stringify(action.get("Currency")),
        "Original_Currency": _stringify(action.get("Currency")),
    }

    row = {name: "" for name in fieldnames}
    for key, value in mapped.items():
        if key in row and value:
            row[key] = value
    return row


def _stringify(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "n/a"}:
        return ""
    return text
