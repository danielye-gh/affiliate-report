from __future__ import annotations

from pathlib import Path

import pandas as pd

from affiliate_report.reconcile.action_rules import normalize_partner_name

PLATFORM_SUMMARY_CONFIG: tuple[tuple[str, str, str], ...] = (
    ("Impact", "Partner", "匹配情况"),
    ("CJ", "Website Name", "Shopify匹配情况"),
    ("Awin-DE", "publisher", "匹配情况"),
    ("Awin-UK", "publisher", "匹配情况"),
)

SUMMARY_COLUMNS = ["Partner/site name", "不匹配", "匹配", "Total"]


def build_match_summary_sheets(
    sheet_sources: dict[str, Path | pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """One summary sheet per platform with matched vs unmatched counts."""
    summaries: dict[str, pd.DataFrame] = {}
    for platform, name_column, match_column in PLATFORM_SUMMARY_CONFIG:
        if platform not in sheet_sources:
            continue
        df = _load_sheet_source(sheet_sources[platform])
        summaries[f"{platform}-Summary"] = _summarize_platform(
            df, platform, name_column, match_column
        )
    return summaries


def _load_sheet_source(source: Path | pd.DataFrame) -> pd.DataFrame:
    if isinstance(source, Path):
        return pd.read_csv(source, dtype=str, keep_default_na=False)
    return source.copy()


def _summarize_platform(
    df: pd.DataFrame,
    platform: str,
    name_column: str,
    match_column: str,
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)

    if name_column not in df.columns:
        raise ValueError(f"{platform} sheet missing '{name_column}' column")
    if match_column not in df.columns:
        raise ValueError(f"{platform} sheet missing '{match_column}' column")

    work = df[[name_column, match_column]].copy()
    work["_name"] = work[name_column].map(normalize_partner_name)
    work["_matched"] = work[match_column].astype(str).str.strip() == "匹配"

    grouped = (
        work.groupby("_name", dropna=False)["_matched"]
        .agg(匹配="sum", Total="count")
        .reset_index()
    )
    grouped["匹配"] = grouped["匹配"].astype(int)
    grouped["Total"] = grouped["Total"].astype(int)
    grouped["不匹配"] = grouped["Total"] - grouped["匹配"]
    grouped.rename(columns={"_name": "Partner/site name"}, inplace=True)

    grouped = grouped.sort_values(["Total", "Partner/site name"], ascending=[False, True])
    return grouped[SUMMARY_COLUMNS].reset_index(drop=True)

