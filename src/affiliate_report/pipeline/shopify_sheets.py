from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from affiliate_report.config import RAW_DIR
from affiliate_report.reconcile.formatting import format_decimal_cell

SHOPIFY_SITES = ("us", "de", "uk")

SHOPIFY_DISPLAY_COLUMNS = [
    "orderUtmSource",
    "orderUtmMedium",
    "orderUtmCampaign",
    "orderId",
    "oid",
    "orderName",
    "discountCode",
    "minute",
    "netSales",
    "shippingCharges",
    "orders",
    "rowKind",
    "eventAt",
]

SHOPIFY_DECIMAL_COLUMNS = ("netSales", "shippingCharges")

REPORT_FOLDERS = {
    "sales_attribution": "sales_attribution",
    "cj_shopify": "cj_shopify",
    "impact_shopify": "impact_shopify",
    "awin_shopify": "awin_shopify",
}


def build_shopify_workbook_sheets(period_label: str) -> dict[str, pd.DataFrame]:
    sheets: dict[str, pd.DataFrame] = {}
    for site in SHOPIFY_SITES:
        path = _shopify_report_path(site, "sales_attribution", period_label)
        sheets[f"sales_attribution-{site}"] = _load_shopify_report(
            path, site=site, include_site=False
        )

    for sheet_name, folder in (
        ("cj-shopify", "cj_shopify"),
        ("impact-shopify", "impact_shopify"),
        ("awin-shopify", "awin_shopify"),
    ):
        frames = []
        for site in SHOPIFY_SITES:
            path = _shopify_report_path(site, folder, period_label)
            if path.is_file():
                frames.append(_load_shopify_report(path, site=site))
        sheets[sheet_name] = (
            pd.concat(frames, ignore_index=True) if frames else _empty_shopify_frame()
        )

    return sheets


def _shopify_report_path(site: str, folder: str, period_label: str) -> Path:
    return RAW_DIR / "shopify" / site / folder / f"{folder}_{period_label}.json"


def _load_shopify_report(path: Path, *, site: str, include_site: bool = True) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Shopify report not found: {path}")

    with path.open(encoding="utf-8") as f:
        payload = json.load(f)

    if not payload:
        return _empty_shopify_frame(site=site if include_site else "")

    df = pd.json_normalize(payload)
    result = pd.DataFrame({col: _series(df, col) for col in SHOPIFY_DISPLAY_COLUMNS})
    if include_site:
        result.insert(0, "site", site)

    for col in SHOPIFY_DECIMAL_COLUMNS:
        result[col] = result[col].map(format_decimal_cell)

    return result.reset_index(drop=True)


def _series(df: pd.DataFrame, column: str) -> pd.Series:
    if column in df.columns:
        return df[column].map(_cell_str)
    return pd.Series([""] * len(df))


def _cell_str(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "n/a"}:
        return ""
    return text


def _empty_shopify_frame(*, site: str = "") -> pd.DataFrame:
    cols = [*SHOPIFY_DISPLAY_COLUMNS]
    if site:
        cols = ["site", *cols]
    return pd.DataFrame(columns=cols)
