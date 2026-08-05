from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from affiliate_report.config import PROCESSED_DIR, RAW_DIR
from affiliate_report.platforms.awin.client import AwinClient
from affiliate_report.platforms.awin.config import AwinConfig
from affiliate_report.platforms.awin.publishers import (
    PUBLISHERS_FILENAME,
    AwinPublishersAPI,
    build_publisher_name_index,
    load_publishers,
    resolve_publisher_name,
    write_publishers,
)
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
    default_shopify_sales_attribution_path,
    load_shopify_order_id_index,
)

AWIN_SITES = ("de", "uk")

AWIN_MATCH_COLUMNS = [
    "shopify匹配",
    "匹配情况",
    "shopify是否退款",
    "shopify退款金额",
    "discount code",
    "Action",
    "Attribution",
]

AWIN_BASE_COLUMN_SOURCES: list[tuple[str, list[str]]] = [
    ("id", ["id"]),
    ("publisher_id", ["publisherId"]),
    ("publisher", []),
    ("sale_amount", ["saleAmount.amount"]),
    ("commission", ["commissionAmount.amount"]),
    ("network_fee", ["networkFee.amount"]),
    ("date", ["transactionDate"]),
    ("commission_status", ["commissionStatus"]),
    ("validation_date", ["validationDate"]),
]

AWIN_TAIL_COLUMN_SOURCES: list[tuple[str, list[str]]] = [
    ("extra", ["orderRef"]),
    ("type", ["type"]),
    ("site_name", ["siteName"]),
    ("URL", ["url"]),
    ("decline_reason", ["declineReason"]),
    ("referer", ["publisherUrl"]),
    ("clickThroughTime", ["clickDate"]),
    ("voucher_code", ["voucherCode"]),
    ("mins_between_click_trans", ["lapseTime"]),
    ("amended", ["amended"]),
    ("amend_reason", ["amendReason"]),
    ("click_ref", ["clickRefs.clickRef"]),
    ("click_device", ["clickDevice"]),
    ("transaction_device", ["transactionDevice"]),
]

AWIN_OUTPUT_COLUMNS = [
    *[name for name, _ in AWIN_BASE_COLUMN_SOURCES],
    *AWIN_MATCH_COLUMNS,
    *[name for name, _ in AWIN_TAIL_COLUMN_SOURCES],
]

AWIN_DECIMAL_COLUMNS = ("sale_amount", "commission", "network_fee")
AWIN_DATETIME_COLUMNS = ("date", "validation_date", "clickThroughTime")
AWIN_BOOL_COLUMNS = ("amended",)


def enrich_awin_with_shopify(
    awin_path: Path,
    shopify_order_id_index: dict,
    *,
    publisher_name_index: dict[str, str] | None = None,
    utm_source: str = "awin",
) -> pd.DataFrame:
    """Add Shopify reconciliation columns on Awin raw export."""
    with awin_path.open(encoding="utf-8") as f:
        payload = json.load(f)

    if not payload:
        return pd.DataFrame(columns=AWIN_OUTPUT_COLUMNS)

    name_index = publisher_name_index or {}
    raw_df = pd.json_normalize(payload)
    base_df = _select_columns(raw_df, AWIN_BASE_COLUMN_SOURCES)
    tail_df = _select_columns(raw_df, AWIN_TAIL_COLUMN_SOURCES)
    base_df["id"] = base_df["id"].astype(str)
    base_df["publisher_id"] = base_df["publisher_id"].astype(str)
    base_df["publisher"] = base_df["publisher_id"].map(
        lambda publisher_id: resolve_publisher_name(publisher_id, name_index)
    )
    tail_df["extra"] = tail_df["extra"].astype(str)

    match_rows = [
        _match_row(order_ref, shopify_order_id_index, utm_source=utm_source)
        for order_ref in tail_df["extra"]
    ]
    match_df = pd.DataFrame(match_rows, columns=AWIN_MATCH_COLUMNS)
    enriched = pd.concat([base_df, match_df, tail_df], axis=1)
    enriched = enriched[AWIN_OUTPUT_COLUMNS]
    enriched = format_decimal_columns(enriched, AWIN_DECIMAL_COLUMNS)
    for col in AWIN_DATETIME_COLUMNS:
        enriched[col] = enriched[col].map(format_datetime_cell)
    for col in AWIN_BOOL_COLUMNS:
        enriched[col] = enriched[col].map(format_bool_cell)
    enriched["mins_between_click_trans"] = enriched["mins_between_click_trans"].map(
        _lapse_time_to_minutes
    )
    enriched = apply_shopify_action_column(enriched, commission_column="commission")
    enriched = apply_exclusive_code_action_rules(
        enriched,
        partner_column="publisher",
        publisher_id_column="publisher_id",
        promo_column="discount code",
    )
    enriched = apply_partner_volume_action_rules(
        enriched,
        partner_column="publisher",
        commission_column="commission",
    )
    return finalize_action_column(enriched)


def process_awin_month(
    period_label: str,
    *,
    site: str = "all",
    awin_path: Path | None = None,
    shopify_path: Path | None = None,
    utm_source: str = "awin",
    output_path: Path | None = None,
) -> dict[str, Path]:
    site_labels = _resolve_awin_sites(site)
    results: dict[str, Path] = {}

    for site_label in site_labels:
        awin_file = awin_path or (RAW_DIR / "awin" / site_label / f"actions_{period_label}.json")
        shopify_file = shopify_path or default_shopify_sales_attribution_path(
            period_label, site=site_label
        )

        if not awin_file.is_file():
            raise FileNotFoundError(f"Awin raw file not found: {awin_file}")
        if not shopify_file.is_file():
            raise FileNotFoundError(
                f"Shopify sales attribution file not found for {site_label}: {shopify_file}"
            )

        publisher_catalog = _load_publisher_catalog(site_label)
        enriched = enrich_awin_with_shopify(
            awin_file,
            load_shopify_order_id_index(shopify_file),
            publisher_name_index=publisher_catalog,
            utm_source=utm_source,
        )

        if output_path is not None and len(site_labels) == 1:
            out = output_path
        else:
            out = PROCESSED_DIR / "awin" / f"awin_actions_{period_label}_{site_label}_enriched.csv"

        out.parent.mkdir(parents=True, exist_ok=True)
        enriched.to_csv(out, index=False)
        results[site_label] = out

    return results


def _resolve_awin_sites(site: str) -> tuple[str, ...]:
    if site == "all":
        return AWIN_SITES
    if site not in AWIN_SITES:
        raise ValueError(f"Unknown Awin site '{site}'. Choose from: all, de, uk")
    return (site,)


def _load_publisher_catalog(site_label: str) -> dict[str, str]:
    catalog_path = RAW_DIR / "awin" / site_label / PUBLISHERS_FILENAME
    if not catalog_path.is_file():
        _fetch_publisher_catalog(site_label, catalog_path)
    return build_publisher_name_index(load_publishers(catalog_path))


def _fetch_publisher_catalog(site_label: str, catalog_path: Path) -> None:
    try:
        config = AwinConfig.from_env()
        site_cfg = config.site_config(site_label)
    except ValueError:
        return

    with AwinClient(config.api_token, verbose=config.verbose) as http:
        publishers = AwinPublishersAPI(http).list_publishers(site_cfg)
    write_publishers(catalog_path, publishers)


def _select_columns(
    raw_df: pd.DataFrame,
    column_sources: list[tuple[str, list[str]]],
) -> pd.DataFrame:
    return pd.DataFrame(
        {out_name: _pick_column(raw_df, aliases) for out_name, aliases in column_sources}
    )


def _pick_column(df: pd.DataFrame, aliases: list[str]) -> pd.Series:
    for name in aliases:
        if name in df.columns:
            return df[name].replace("", pd.NA).fillna("")
    return pd.Series([""] * len(df))


def _lapse_time_to_minutes(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        seconds = int(float(text))
    except ValueError:
        return text
    return str(seconds // 60)


def _match_row(
    order_ref: object,
    shopify_index: dict,
    *,
    utm_source: str,
) -> dict[str, str]:
    empty = {col: "" for col in AWIN_MATCH_COLUMNS}
    key = str(order_ref or "").strip()
    if not key:
        return empty

    shopify = shopify_index.get(key)
    if shopify is None:
        return empty

    attribution = (shopify.utm_source or "").strip()
    discount_code = (shopify.discount_code or "").strip()
    # Order exists in Shopify: always fill refund fields (utm match is separate).
    refund_fields = {
        "shopify是否退款": shopify.refund_status,
        "shopify退款金额": shopify.refund_amount_cell,
        "Attribution": attribution,
        "discount code": discount_code,
    }
    if not shopify.matches_utm_source(utm_source):
        return {**empty, **refund_fields}

    return {
        "shopify匹配": shopify.oid,
        "匹配情况": "匹配",
        **refund_fields,
        "Action": "",
    }
