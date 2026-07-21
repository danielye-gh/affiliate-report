from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

# Column order aligned with Petlibro CJ-Shopify / Sales Attribution-US sheets.
ATTRIBUTION_COLUMNS = [
    "order_utm_source",
    "order_utm_medium",
    "order_utm_campaign",
    "order_id",
    "oid",
    "order_name",
    "discount_code",
    "minute",
    "net_sales",
    "shipping_charges",
    "orders",
]


def preprocess_shopify_attribution(
    raw_path: Path,
    period_label: str,
    *,
    report: str,
    site: str,
) -> pd.DataFrame:
    if raw_path.stat().st_size == 0:
        return _empty_frame(period_label, report=report, site=site)

    with raw_path.open(encoding="utf-8") as f:
        payload = json.load(f)

    if not payload:
        return _empty_frame(period_label, report=report, site=site)

    df = pd.json_normalize(payload)
    result = pd.DataFrame(
        {
            "platform": "shopify",
            "site": site,
            "report": report,
            "period": period_label,
            "order_utm_source": df.get("orderUtmSource", pd.Series([pd.NA] * len(df))),
            "order_utm_medium": df.get("orderUtmMedium", pd.Series([pd.NA] * len(df))),
            "order_utm_campaign": df.get("orderUtmCampaign", pd.Series([pd.NA] * len(df))),
            "order_id": df.get("orderId", pd.Series([pd.NA] * len(df))).astype(str),
            "oid": df.get("oid", pd.Series([pd.NA] * len(df))).astype(str),
            "order_name": df.get("orderName", pd.Series([pd.NA] * len(df))),
            "discount_code": df.get("discountCode", pd.Series([pd.NA] * len(df))),
            "minute": df.get("minute", pd.Series([pd.NA] * len(df))),
            "net_sales": df.get("netSales", pd.Series([None] * len(df))).map(_to_decimal),
            "shipping_charges": df.get("shippingCharges", pd.Series([None] * len(df))).map(
                _to_decimal
            ),
            "orders": df.get("orders", pd.Series([pd.NA] * len(df))),
            "row_kind": df.get("rowKind", pd.Series([pd.NA] * len(df))),
            "event_at": pd.to_datetime(df.get("eventAt"), errors="coerce", utc=True),
        }
    )
    return result.reset_index(drop=True)


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


def _empty_frame(period_label: str, *, report: str, site: str) -> pd.DataFrame:
    cols = [
        "platform",
        "site",
        "report",
        "period",
        *ATTRIBUTION_COLUMNS,
        "row_kind",
        "event_at",
    ]
    return pd.DataFrame(columns=cols).assign(
        platform="shopify",
        site=site,
        report=report,
        period=period_label,
    )
