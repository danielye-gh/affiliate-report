from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

# Impact CSV column names vary by report handle; map common variants to standard schema.
COLUMN_ALIASES: dict[str, list[str]] = {
    "action_id": ["Action Id", "Action ID", "ActionId", "Id"],
    "order_id": ["OID", "Order Id", "Order ID", "Oid"],
    "event_date": ["Action Date", "EventDate", "ActionDate"],
    "state": ["Status", "State"],
    "revenue": ["Revenue", "Sale Amount", "Amount", "SaleAmount"],
    "commission": ["Action Cost", "Action Earnings", "Payout", "Client Cost"],
    "currency": ["Currency", "Sale Currency"],
    "campaign_id": ["Campaign Id", "Campaign ID", "CampaignId", "Program Id"],
    "campaign_name": ["Campaign", "Campaign Name", "CampaignName", "Brand"],
    "partner_id": ["Partner ID", "Partner Id", "MediaPartnerId"],
    "partner_name": ["Partner", "MediaPartnerName"],
    "event_type": ["Event Type", "Action Tracker Name", "ActionTrackerName"],
    "sub_id_1": ["Sub ID 1", "SubId1", "Sub Id 1"],
    "sub_id_2": ["Sub ID 2", "SubId2", "Sub Id 2"],
    "sub_id_3": ["Sub ID 3", "SubId3", "Sub Id 3"],
}


def preprocess_impact_actions(raw_path: Path, period_label: str) -> pd.DataFrame:
    """Normalize Impact raw CSV/JSON export to standard columns."""
    if raw_path.suffix.lower() == ".json":
        df = pd.read_json(raw_path)
    else:
        df = pd.read_csv(raw_path, dtype=str, keep_default_na=False)

    if df.empty:
        return _empty_frame(period_label)

    normalized: dict[str, pd.Series] = {"platform": pd.Series(["impact"] * len(df)), "period": period_label}

    for target, aliases in COLUMN_ALIASES.items():
        normalized[target] = _pick_column(df, aliases)

    result = pd.DataFrame(normalized)
    result["revenue"] = result["revenue"].map(_to_decimal)
    result["commission"] = result["commission"].map(_to_decimal)
    result["event_date"] = pd.to_datetime(result["event_date"], errors="coerce", utc=True)

    # Drop rows without action_id when present
    if result["action_id"].notna().any():
        result = result[result["action_id"].astype(str).str.len() > 0]

    return result.reset_index(drop=True)


def _pick_column(df: pd.DataFrame, aliases: list[str]) -> pd.Series:
    for name in aliases:
        if name in df.columns:
            return df[name].replace("", pd.NA)
    return pd.Series([pd.NA] * len(df))


def _to_decimal(value: object) -> Decimal | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().replace(",", "").replace("$", "")
    if not text or text.lower() in {"nan", "none", "n/a"}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _empty_frame(period_label: str) -> pd.DataFrame:
    cols = [
        "platform",
        "period",
        "action_id",
        "order_id",
        "event_date",
        "state",
        "revenue",
        "commission",
        "currency",
        "campaign_id",
        "campaign_name",
        "partner_id",
        "partner_name",
        "event_type",
        "sub_id_1",
        "sub_id_2",
        "sub_id_3",
    ]
    return pd.DataFrame(columns=cols).assign(platform="impact", period=period_label)
