from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


def _progress(message: str) -> None:
    print(message, flush=True)

from affiliate_report.config import DATA_DIR
from affiliate_report.models import MonthRange
from affiliate_report.platforms.awin import AwinPlatformClient
# from affiliate_report.platforms.cj import CJPlatformClient  # CJ disabled
from affiliate_report.platforms.impact import ImpactPlatformClient
from affiliate_report.platforms.shopify import ShopifyPlatformClient
from affiliate_report.pipeline.match_summary import build_match_summary_sheets
from affiliate_report.pipeline.shopify_sheets import (
    SHOPIFY_DECIMAL_COLUMNS,
    build_shopify_workbook_sheets,
)
from affiliate_report.reconcile.awin import AWIN_DECIMAL_COLUMNS, process_awin_month
# from affiliate_report.reconcile.cj import CJ_DECIMAL_COLUMNS, process_cj_month  # CJ disabled
from affiliate_report.reconcile.impact import IMPACT_DECIMAL_COLUMNS, process_impact_month

REPORTS_DIR = DATA_DIR / "reports"

# Amount columns that must be written as real numbers (not text) in Excel.
NUMERIC_COLUMNS: frozenset[str] = frozenset(
    {
        *IMPACT_DECIMAL_COLUMNS,
        # *CJ_DECIMAL_COLUMNS,  # CJ disabled
        *AWIN_DECIMAL_COLUMNS,
        *SHOPIFY_DECIMAL_COLUMNS,
    }
)

NUMERIC_DISPLAY_FORMAT = "0.00"


@dataclass(frozen=True)
class MonthlyReportResult:
    output_path: Path
    sheet_sources: dict[str, Path | pd.DataFrame]


def default_monthly_report_path(period_label: str) -> Path:
    return REPORTS_DIR / f"affiliate_report_{period_label}.xlsx"


def build_monthly_report(
    month: MonthRange,
    *,
    output_path: Path | None = None,
    skip_fetch: bool = False,
    verbose: bool = False,
    impact_method: str = "report",
    impact_report_handle: str | None = None,
) -> MonthlyReportResult:
    """Fetch platform data, reconcile with Shopify, export one Excel workbook."""
    _progress(f"=== Monthly report {month.label} ===")

    if not skip_fetch:
        _fetch_monthly_sources(
            month,
            verbose=verbose,
            impact_method=impact_method,
            impact_report_handle=impact_report_handle,
        )
    else:
        _progress("Skipping API fetch (--skip-fetch); using existing data/raw/")

    sheet_sources = _process_monthly_sheets(month)
    out = output_path or default_monthly_report_path(month.label)
    out.parent.mkdir(parents=True, exist_ok=True)
    _progress(f"Writing Excel workbook: {out}")
    _write_workbook(out, sheet_sources)
    _progress(f"Done: {out}")
    return MonthlyReportResult(output_path=out, sheet_sources=sheet_sources)


def _fetch_monthly_sources(
    month: MonthRange,
    *,
    verbose: bool,
    impact_method: str,
    impact_report_handle: str | None,
) -> None:
    _progress("--- Fetch Shopify (all sites) ---")
    shopify = ShopifyPlatformClient(verbose=verbose)
    shopify.fetch_monthly_reports_by_site(
        month,
        site=None,
        reports=("all",),
    )

    _progress("--- Fetch Impact ---")
    impact = ImpactPlatformClient(verbose=verbose)
    impact.fetch_monthly_actions(
        month,
        method=impact_method,
        report_handle=impact_report_handle,
    )

    # CJ disabled — uncomment to re-enable
    # _progress("--- Fetch CJ ---")
    # cj = CJPlatformClient(verbose=verbose)
    # cj.fetch_monthly_actions(month)

    _progress("--- Fetch Awin (DE + UK) ---")
    awin = AwinPlatformClient(verbose=verbose)
    awin.fetch_monthly_actions_by_site(month, site=None)


def _process_monthly_sheets(month: MonthRange) -> dict[str, Path | pd.DataFrame]:
    label = month.label
    _progress("--- Reconcile Impact ---")
    sources: dict[str, Path | pd.DataFrame] = {
        "Impact": process_impact_month(label),
    }
    # CJ disabled — uncomment to re-enable
    # _progress("--- Reconcile CJ ---")
    # sources["CJ"] = process_cj_month(label, shopify_site="all")
    _progress("--- Reconcile Awin ---")
    awin_paths = process_awin_month(label, site="all")
    sources["Awin-DE"] = awin_paths["de"]
    sources["Awin-UK"] = awin_paths["uk"]
    _progress("--- Build Shopify sheets ---")
    sources.update(build_shopify_workbook_sheets(label))
    _progress("--- Build match summaries ---")
    summaries = build_match_summary_sheets(sources)
    return {**summaries, **sources}


def _write_workbook(output_path: Path, sheet_sources: dict[str, Path | pd.DataFrame]) -> None:
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name, source in sheet_sources.items():
            _progress(f"  sheet: {sheet_name}")
            if isinstance(source, Path):
                df = pd.read_csv(source, dtype=str, keep_default_na=False)
            else:
                df = source.copy()

            numeric_cols = [col for col in df.columns if col in NUMERIC_COLUMNS]
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df.to_excel(writer, sheet_name=sheet_name, index=False)
            _apply_numeric_format(writer.sheets[sheet_name], df, numeric_cols)


def _apply_numeric_format(worksheet, df: pd.DataFrame, numeric_cols: list[str]) -> None:
    """Display amount columns with two decimals while keeping them numeric."""
    from openpyxl.utils import get_column_letter

    for col in numeric_cols:
        column_letter = get_column_letter(df.columns.get_loc(col) + 1)
        for cell in worksheet[column_letter][1:]:  # skip header row
            if cell.value is not None:
                cell.number_format = NUMERIC_DISPLAY_FORMAT
