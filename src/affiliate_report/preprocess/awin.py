from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd


def preprocess_awin_actions(raw_path: Path, period_label: str, *, site: str) -> pd.DataFrame:
    """Normalize Awin raw JSON export to standard columns."""
    if raw_path.stat().st_size == 0:
        return _empty_frame(period_label, site)

    with raw_path.open(encoding="utf-8") as f:
        payload = json.load(f)

    if not payload:
        return _empty_frame(period_label, site)

    df = pd.json_normalize(payload)
    result = pd.DataFrame(
        {
            "platform": "awin",
            "site": site,
            "period": period_label,
            "action_id": df.get("id", pd.Series([pd.NA] * len(df))).astype(str),
            "order_id": df.get("orderRef", pd.Series([pd.NA] * len(df))),
            "event_date": pd.to_datetime(df.get("transactionDate"), errors="coerce", utc=True),
            "state": df.get("commissionStatus", pd.Series([pd.NA] * len(df))),
            "revenue": _amount_series(df, "saleAmount.amount"),
            "commission": _amount_series(df, "commissionAmount.amount"),
            "currency": _pick_nested(df, "saleAmount.currency", "commissionAmount.currency"),
            "campaign_id": df.get("campaign", pd.Series([pd.NA] * len(df))),
            "campaign_name": pd.NA,
            "partner_id": df.get("publisherId", pd.Series([pd.NA] * len(df))).astype(str),
            "partner_name": df.get("siteName", pd.Series([pd.NA] * len(df))),
            "event_type": df.get("type", pd.Series([pd.NA] * len(df))),
            "sub_id_1": _click_ref_series(df),
            "sub_id_2": _custom_param_series(df, "2"),
            "sub_id_3": _custom_param_series(df, "3"),
        }
    )

    result = result[result["action_id"].astype(str).str.len() > 0]
    return result.reset_index(drop=True)


def _amount_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series([None] * len(df))
    return df[column].map(_to_decimal)


def _pick_nested(df: pd.DataFrame, *columns: str) -> pd.Series:
    for column in columns:
        if column in df.columns:
            return df[column].replace("", pd.NA)
    return pd.Series([pd.NA] * len(df))


def _click_ref_series(df: pd.DataFrame) -> pd.Series:
    if "clickRefs.clickRef" in df.columns:
        return df["clickRefs.clickRef"].replace("", pd.NA)
    return pd.Series([pd.NA] * len(df))


def _custom_param_series(df: pd.DataFrame, key: str) -> pd.Series:
    if "customParameters" not in df.columns:
        return pd.Series([pd.NA] * len(df))

    def extract(row: object) -> object:
        if not isinstance(row, list):
            return pd.NA
        for item in row:
            if isinstance(item, dict) and str(item.get("key")) == key:
                return item.get("value")
        return pd.NA

    return df["customParameters"].map(extract)


def _to_decimal(value: object) -> Decimal | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "n/a"}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _empty_frame(period_label: str, site: str) -> pd.DataFrame:
    cols = [
        "platform",
        "site",
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
    return pd.DataFrame(columns=cols).assign(platform="awin", site=site, period=period_label)
