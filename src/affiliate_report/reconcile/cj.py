from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from affiliate_report.config import PROCESSED_DIR, RAW_DIR
from affiliate_report.exclusive_codes import apply_exclusive_code_action_rules
from affiliate_report.reconcile.action_rules import apply_partner_volume_action_rules
from affiliate_report.reconcile.formatting import (
    apply_shopify_action_column,
    finalize_action_column,
    format_bool_cell,
    format_datetime_cell,
    format_decimal_columns,
)
from affiliate_report.reconcile.shopify import (
    load_order_id_indexes_for_process,
    lookup_order_id_match,
)

CJ_MATCH_COLUMNS = [
    "Shopify匹配",
    "Shopify匹配情况",
    "shopify是否退款",
    "shopify退款金额",
    "20开头OID-Shopify",
    "discount code",
    "Impact匹配",
    "Action",
]

CJ_DETAIL_COLUMN_SOURCES: list[tuple[str, list[str]]] = [
    ("Commission ID", ["commissionId"]),
    ("Posting Date", ["postingDate"]),
    ("Event Date", ["eventDate"]),
    ("Publisher CID", ["publisherId"]),
    ("Publisher Name", ["publisherName"]),
    ("Website Name", ["websiteName"]),
    ("Action Name", ["actionTrackerName"]),
    ("Action Type", ["actionType"]),
    ("Status", ["status", "actionStatus"]),
    ("Sale Amount (USD)", ["saleAmountUsd"]),
    ("Corrected Amount (USD)", ["correctedAmountUsd"]),
    ("Order Discount (USD)", ["orderDiscountUsd"]),
    ("Advertiser Commission (USD)", ["advertiserCommissionUsd", "advCommissionAmountUsd"]),
    ("Publisher Commission (USD)", ["pubCommissionAmountUsd"]),
    ("CJ Fee (USD)", ["cjFeeUsd"]),
    ("Ad ID", ["linkId", "aid"]),
    ("Coupon", ["coupon"]),
    ("New to File", ["newToFile"]),
    ("Is Cross-Device", ["isCrossDevice"]),
]

CJ_OUTPUT_COLUMNS = [
    "Order ID",
    *CJ_MATCH_COLUMNS,
    *[name for name, _ in CJ_DETAIL_COLUMN_SOURCES],
]

CJ_DECIMAL_COLUMNS = (
    "Sale Amount (USD)",
    "Corrected Amount (USD)",
    "Order Discount (USD)",
    "Advertiser Commission (USD)",
    "Publisher Commission (USD)",
    "CJ Fee (USD)",
)

CJ_DATETIME_COLUMNS = ("Posting Date", "Event Date")
CJ_BOOL_COLUMNS = ("New to File", "Is Cross-Device")


def enrich_cj_with_shopify(
    cj_path: Path,
    shopify_order_id_indexes: dict,
    *,
    utm_source: str = "cj",
    order_id_column: str = "orderId",
) -> pd.DataFrame:
    """Add Shopify reconciliation columns after Order ID on CJ raw export."""
    with cj_path.open(encoding="utf-8") as f:
        payload = json.load(f)

    if not payload:
        return pd.DataFrame(columns=CJ_OUTPUT_COLUMNS)

    raw_df = pd.json_normalize(payload)
    cj_df = _select_cj_columns(raw_df, order_id_column=order_id_column)
    match_rows = [
        _match_row(order_id, shopify_order_id_indexes, utm_source=utm_source)
        for order_id in cj_df["Order ID"]
    ]
    match_df = pd.DataFrame(match_rows, columns=CJ_MATCH_COLUMNS)
    enriched = pd.concat([cj_df, match_df], axis=1)
    enriched = enriched[CJ_OUTPUT_COLUMNS]
    enriched = format_decimal_columns(enriched, CJ_DECIMAL_COLUMNS)
    for col in CJ_DATETIME_COLUMNS:
        enriched[col] = enriched[col].map(format_datetime_cell)
    for col in CJ_BOOL_COLUMNS:
        enriched[col] = enriched[col].map(format_bool_cell)
    enriched = apply_shopify_action_column(
        enriched,
        match_column="Shopify匹配情况",
        commission_column="CJ Fee (USD)",
    )
    enriched = apply_exclusive_code_action_rules(
        enriched,
        partner_column="Website Name",
        publisher_id_column="Publisher CID",
        promo_column="discount code",
        match_column="Shopify匹配情况",
    )
    enriched = apply_partner_volume_action_rules(
        enriched,
        partner_column="Website Name",
        commission_column="CJ Fee (USD)",
    )
    return finalize_action_column(enriched)


def process_cj_month(
    period_label: str,
    *,
    cj_path: Path | None = None,
    shopify_path: Path | None = None,
    shopify_site: str = "all",
    utm_source: str = "cj",
    output_path: Path | None = None,
) -> Path:
    cj_file = cj_path or (RAW_DIR / "cj" / f"actions_{period_label}.json")

    if not cj_file.is_file():
        raise FileNotFoundError(f"CJ raw file not found: {cj_file}")

    shopify_indexes = load_order_id_indexes_for_process(
        period_label,
        shopify_path=shopify_path,
        shopify_site=shopify_site,
    )

    enriched = enrich_cj_with_shopify(cj_file, shopify_indexes, utm_source=utm_source)
    out = output_path or (PROCESSED_DIR / "cj" / f"cj_actions_{period_label}_enriched.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    enriched.to_csv(out, index=False)
    return out


def _select_cj_columns(raw_df: pd.DataFrame, *, order_id_column: str) -> pd.DataFrame:
    if order_id_column not in raw_df.columns and "orderId" in raw_df.columns:
        order_id_column = "orderId"
    if order_id_column not in raw_df.columns:
        raise ValueError(f"CJ file missing '{order_id_column}' column")

    result = {"Order ID": _pick_column(raw_df, [order_id_column]).astype(str)}
    for out_name, aliases in CJ_DETAIL_COLUMN_SOURCES:
        result[out_name] = _pick_column(raw_df, aliases)
    return pd.DataFrame(result)


def _pick_column(df: pd.DataFrame, aliases: list[str]) -> pd.Series:
    for name in aliases:
        if name in df.columns:
            return df[name].replace("", pd.NA).fillna("")
    return pd.Series([""] * len(df))


def _match_row(
    cj_order_id: object,
    shopify_indexes: dict,
    *,
    utm_source: str,
) -> dict[str, str]:
    empty = {col: "" for col in CJ_MATCH_COLUMNS}
    order_id = str(cj_order_id or "").strip()
    if not order_id:
        return empty

    shopify = lookup_order_id_match(order_id, shopify_indexes)
    if shopify is None:
        return empty

    discount_code = (shopify.discount_code or "").strip()
    # Order exists in Shopify: always fill refund fields (utm match is separate).
    refund_fields = {
        "shopify是否退款": shopify.refund_status,
        "shopify退款金额": shopify.refund_amount_cell,
        "discount code": discount_code,
    }
    if not shopify.matches_utm_source(utm_source):
        return {**empty, **refund_fields}

    return {
        "Shopify匹配": shopify.oid,
        "Shopify匹配情况": "匹配",
        **refund_fields,
        "20开头OID-Shopify": shopify.oid,
        "Impact匹配": "",
        "Action": "",
    }
