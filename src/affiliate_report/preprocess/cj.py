from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd


def preprocess_cj_actions(raw_path: Path, period_label: str) -> pd.DataFrame:
    """Normalize CJ raw JSON export to standard + Commission Detail CSV columns."""
    if raw_path.stat().st_size == 0:
        return _empty_frame(period_label)

    with raw_path.open(encoding="utf-8") as f:
        payload = json.load(f)

    if not payload:
        return _empty_frame(period_label)

    df = pd.json_normalize(payload)

    result = pd.DataFrame(
        {
            "platform": "cj",
            "period": period_label,
            # Standard cross-platform columns
            "action_id": _series(df, "commissionId").astype(str),
            "order_id": _series(df, "orderId").astype(str),
            "event_date": pd.to_datetime(_series(df, "eventDate"), errors="coerce", utc=True),
            "state": _series(df, "status", "actionStatus"),
            "revenue": _amount_series(df, "saleAmountUsd").map(_to_decimal),
            "commission": _amount_series(
                df, "advertiserCommissionUsd", "advCommissionAmountUsd"
            ).map(_to_decimal),
            "order_discount": _amount_series(df, "orderDiscountUsd").map(_to_decimal),
            "currency": pd.Series(["USD"] * len(df)),
            "campaign_id": _series(df, "advertiserId").astype(str),
            "campaign_name": _series(df, "advertiserName"),
            "partner_id": _series(df, "publisherId").astype(str),
            "partner_name": _series(df, "publisherName"),
            "event_type": _series(df, "actionTrackerName"),
            "sub_id_1": _series(df, "shopperId", "linkId", "aid"),
            "sub_id_2": _series(df, "websiteId", "sid"),
            "sub_id_3": _series(df, "sid"),
            # CJ Commission Detail CSV-aligned columns
            "posting_date": pd.to_datetime(_series(df, "postingDate"), errors="coerce", utc=True),
            "website_name": _series(df, "websiteName"),
            "advertiser_commission_usd": _amount_series(
                df, "advertiserCommissionUsd", "advCommissionAmountUsd"
            ).map(_to_decimal),
            "action_type": _series(df, "actionType"),
            "status": _series(df, "status", "actionStatus"),
            "sale_amount_usd": _amount_series(df, "saleAmountUsd").map(_to_decimal),
            "corrected_amount_usd": _amount_series(df, "correctedAmountUsd").map(_to_decimal),
            "publisher_commission_usd": _amount_series(df, "pubCommissionAmountUsd").map(
                _to_decimal
            ),
            "cj_fee_usd": _amount_series(df, "cjFeeUsd").map(_to_decimal),
            "link_id": _series(df, "linkId", "aid"),
            "coupon": _series(df, "coupon"),
            "new_to_file": _series(df, "newToFile"),
            "is_cross_device": _series(df, "isCrossDevice"),
            "original": _series(df, "original"),
        }
    )

    result = result[result["action_id"].astype(str).str.len() > 0]
    return result.reset_index(drop=True)


def _series(df: pd.DataFrame, *columns: str) -> pd.Series:
    for column in columns:
        if column in df.columns:
            return df[column].replace("", pd.NA)
    return pd.Series([pd.NA] * len(df))


def _amount_series(df: pd.DataFrame, *columns: str) -> pd.Series:
    for column in columns:
        if column in df.columns:
            return df[column]
    return pd.Series([None] * len(df))


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
        "order_discount",
        "currency",
        "campaign_id",
        "campaign_name",
        "partner_id",
        "partner_name",
        "event_type",
        "sub_id_1",
        "sub_id_2",
        "sub_id_3",
        "posting_date",
        "website_name",
        "advertiser_commission_usd",
        "action_type",
        "status",
        "sale_amount_usd",
        "corrected_amount_usd",
        "publisher_commission_usd",
        "cj_fee_usd",
        "link_id",
        "coupon",
        "new_to_file",
        "is_cross_device",
        "original",
    ]
    return pd.DataFrame(columns=cols).assign(platform="cj", period=period_label)
