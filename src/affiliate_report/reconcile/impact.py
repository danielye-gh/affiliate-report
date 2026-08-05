from __future__ import annotations

from pathlib import Path

import pandas as pd

from affiliate_report.config import PROCESSED_DIR, RAW_DIR
from affiliate_report.exclusive_codes import apply_exclusive_code_action_rules
from affiliate_report.reconcile.action_rules import apply_partner_volume_action_rules
from affiliate_report.reconcile.formatting import (
    apply_shopify_action_column,
    finalize_action_column,
    format_decimal_columns,
)
from affiliate_report.reconcile.shopify import (
    load_oid_indexes_for_process,
    lookup_oid_match,
)

IMPACT_MATCH_COLUMNS = [
    "shopify匹配",
    "匹配情况",
    "shopify是否退款",
    "shopify退款金额",
    "62开头OID-shopify",
    "attribution",
    "discount code",
    "CJ匹配",
    "Action",
    "CJ Action状态",
]

# Output label -> raw Impact export column aliases (ReportExport CSV uses underscores).
IMPACT_BASE_COLUMN_SOURCES: list[tuple[str, list[str]]] = [
    ("Action Date", ["Action_Date", "Action Date", "ActionDate"]),
    ("Action Id", ["Action_Id", "Action Id", "ActionId", "Action ID"]),
    ("OID", ["OID", "Order Id", "Order ID", "Oid"]),
    ("Status", ["Status", "State"]),
    ("Revenue", ["Sale_Amount", "Sale Amount", "Revenue", "Amount", "SaleAmount"]),
    ("Action Cost", ["Payout", "Action Cost", "Action Earnings", "Client Cost"]),
    ("Rate", ["Rate"]),
    ("Promo Code", ["Promo_Code", "Promo Code"]),
    ("Partner", ["Media_Partner", "Partner", "MediaPartnerName"]),
    ("Partner Id", ["mp_id", "Partner Id", "Partner ID", "PartnerId", "MediaPartnerId"]),
    ("Event Type", ["Action_Tracker", "Event Type", "Action Tracker Name", "ActionTrackerName"]),
    ("Event Type Id", ["AT_Id", "Event Type Id", "Action Tracker Id", "ActionTrackerId"]),
]

IMPACT_OUTPUT_COLUMNS = [
    "Action Date",
    "Action Id",
    "OID",
    *IMPACT_MATCH_COLUMNS,
    "Status",
    "Revenue",
    "Action Cost",
    "Rate",
    "Promo Code",
    "Partner",
    "Partner Id",
    "Event Type",
    "Event Type Id",
]

IMPACT_DECIMAL_COLUMNS = ("Revenue", "Action Cost", "Rate")


def enrich_impact_with_shopify(
    impact_path: Path,
    shopify_oid_indexes: dict,
    *,
    utm_source: str = "impact",
    oid_column: str = "OID",
) -> pd.DataFrame:
    """Add Shopify reconciliation columns after OID on Impact raw export."""
    raw_df = pd.read_csv(impact_path, dtype=str, keep_default_na=False)
    if raw_df.empty:
        return pd.DataFrame(columns=IMPACT_OUTPUT_COLUMNS)

    impact_df = _select_impact_base_columns(raw_df)
    if oid_column not in impact_df.columns and "OID" in impact_df.columns:
        oid_column = "OID"
    if oid_column not in impact_df.columns:
        raise ValueError(f"Impact file missing '{oid_column}' column: {impact_path}")

    match_rows = [
        _match_row(oid, shopify_oid_indexes, utm_source=utm_source)
        for oid in impact_df[oid_column]
    ]
    match_df = pd.DataFrame(match_rows, columns=IMPACT_MATCH_COLUMNS)
    enriched = pd.concat([impact_df, match_df], axis=1)
    enriched = format_decimal_columns(enriched[IMPACT_OUTPUT_COLUMNS], IMPACT_DECIMAL_COLUMNS)
    enriched = apply_shopify_action_column(enriched, commission_column="Action Cost")
    enriched = apply_exclusive_code_action_rules(
        enriched,
        partner_column="Partner",
        publisher_id_column="Partner Id",
        promo_column="discount code",
    )
    enriched = apply_partner_volume_action_rules(
        enriched,
        partner_column="Partner",
        commission_column="Action Cost",
    )
    return finalize_action_column(enriched)


def process_impact_month(
    period_label: str,
    *,
    impact_path: Path | None = None,
    shopify_path: Path | None = None,
    shopify_site: str = "all",
    utm_source: str = "impact",
    output_path: Path | None = None,
) -> Path:
    impact_file = impact_path or (RAW_DIR / "impact" / f"actions_{period_label}.csv")

    if not impact_file.is_file():
        raise FileNotFoundError(f"Impact raw file not found: {impact_file}")

    shopify_indexes = load_oid_indexes_for_process(
        period_label,
        shopify_path=shopify_path,
        shopify_site=shopify_site,
    )

    enriched = enrich_impact_with_shopify(
        impact_file,
        shopify_indexes,
        utm_source=utm_source,
    )

    out = output_path or (PROCESSED_DIR / "impact" / f"impact_actions_{period_label}_enriched.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    enriched.to_csv(out, index=False)
    return out


def _select_impact_base_columns(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {out_name: _pick_column(df, aliases) for out_name, aliases in IMPACT_BASE_COLUMN_SOURCES}
    )


def _pick_column(df: pd.DataFrame, aliases: list[str]) -> pd.Series:
    for name in aliases:
        if name in df.columns:
            return df[name].replace("", pd.NA).fillna("")
    return pd.Series([""] * len(df))


def _match_row(
    impact_oid: object,
    shopify_indexes: dict,
    *,
    utm_source: str,
) -> dict[str, str]:
    empty = {col: "" for col in IMPACT_MATCH_COLUMNS}
    oid = str(impact_oid or "").strip()
    if not oid:
        return empty

    shopify = lookup_oid_match(oid, shopify_indexes)
    if shopify is None:
        return empty

    attribution = (shopify.utm_source or "").strip()
    discount_code = (shopify.discount_code or "").strip()
    if not shopify.matches_utm_source(utm_source):
        return {**empty, "attribution": attribution, "discount code": discount_code}

    return {
        "shopify匹配": shopify.oid,
        "匹配情况": "匹配",
        "shopify是否退款": shopify.refund_status,
        "shopify退款金额": shopify.refund_amount_cell,
        "62开头OID-shopify": shopify.order_id,
        "attribution": attribution,
        "discount code": discount_code,
        "CJ匹配": "",
        "Action": "",
        "CJ Action状态": "",
    }
