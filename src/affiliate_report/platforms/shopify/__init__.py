from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from affiliate_report.base.client import AffiliatePlatformClient
from affiliate_report.config import ensure_data_dirs
from affiliate_report.models import MonthRange
from affiliate_report.platforms.shopify.client import ShopifyClient
from affiliate_report.platforms.shopify.config import ShopifyConfig, ShopifySiteConfig
from affiliate_report.platforms.shopify.orders import ShopifyOrdersAPI
from affiliate_report.preprocess.shopify import preprocess_shopify_attribution

REPORT_SALES_ATTRIBUTION = "sales-attribution"
REPORT_CJ_SHOPIFY = "cj-shopify"
REPORT_IMPACT_SHOPIFY = "impact-shopify"
REPORT_AWIN_SHOPIFY = "awin-shopify"
ALL_REPORTS = (
    REPORT_SALES_ATTRIBUTION,
    REPORT_CJ_SHOPIFY,
    REPORT_IMPACT_SHOPIFY,
    REPORT_AWIN_SHOPIFY,
)


class ShopifyPlatformClient(AffiliatePlatformClient):
    platform_name = "shopify"

    def __init__(self, config: ShopifyConfig | None = None, *, verbose: bool | None = None):
        self.config = config or ShopifyConfig.from_env()
        self.verbose = self.config.verbose if verbose is None else verbose

    def _http_client(self, site: ShopifySiteConfig) -> ShopifyClient:
        return ShopifyClient(
            site,
            api_version=self.config.api_version,
            verbose=self.verbose,
        )

    def fetch_monthly_actions(
        self,
        month: MonthRange,
        *,
        output_dir: Path | None = None,
        site: str | None = None,
        reports: tuple[str, ...] | None = None,
    ) -> Path:
        paths = self.fetch_monthly_reports_by_site(month, site=site, reports=reports)
        if len(paths) == 1:
            return next(iter(paths.values()))
        raw_root = output_dir or ensure_data_dirs(self.platform_name)[0]
        return raw_root

    def fetch_monthly_reports_by_site(
        self,
        month: MonthRange,
        *,
        site: str | None = None,
        reports: tuple[str, ...] | None = None,
        output_dir: Path | None = None,
    ) -> dict[str, Path]:
        selected = _resolve_reports(reports)
        site_configs = self.config.resolve_sites(site)
        results: dict[str, Path] = {}

        for site_cfg in site_configs:
            with self._http_client(site_cfg) as http:
                api = ShopifyOrdersAPI(http, self.config)
                all_rows = api.list_attribution_rows_for_month(month)

                report_rows = {
                    REPORT_SALES_ATTRIBUTION: all_rows,
                    REPORT_CJ_SHOPIFY: api.filter_rows(all_rows, self.config.cj_utm),
                    REPORT_IMPACT_SHOPIFY: api.filter_rows(all_rows, self.config.impact_utm),
                    REPORT_AWIN_SHOPIFY: api.filter_rows(all_rows, self.config.awin_utm),
                }

                for report_name in selected:
                    raw_dir = _site_raw_dir(output_dir, site_cfg, report_name)
                    raw_dir.mkdir(parents=True, exist_ok=True)
                    filename = _report_filename(report_name, month.label)
                    out_path = raw_dir / filename
                    _write_rows(out_path, report_rows[report_name])
                    results[f"{site_cfg.label}/{report_name}"] = out_path

        return results

    def preprocess_actions(self, raw_path: Path, month: MonthRange) -> pd.DataFrame:
        report = _report_from_path(raw_path)
        parts = raw_path.parts
        site = "us"
        if "shopify" in parts:
            site = parts[parts.index("shopify") + 1]
        return preprocess_shopify_attribution(raw_path, month.label, report=report, site=site)

    def fetch_and_preprocess(
        self,
        month: MonthRange,
        *,
        site: str | None = None,
        reports: tuple[str, ...] | None = None,
    ) -> tuple[dict[str, Path], dict[str, Path]]:
        raw_paths = self.fetch_monthly_reports_by_site(month, site=site, reports=reports)
        processed_paths: dict[str, Path] = {}

        for key, raw_path in raw_paths.items():
            df = self.preprocess_actions(raw_path, month)
            site_label, _report_name = key.split("/", 1)
            _, processed_dir = ensure_data_dirs(self.platform_name, site_label)
            processed_path = processed_dir / raw_path.name.replace(".json", ".parquet")
            df.to_parquet(processed_path, index=False)
            processed_paths[key] = processed_path

        return raw_paths, processed_paths


def _resolve_reports(reports: tuple[str, ...] | None) -> tuple[str, ...]:
    if not reports or reports == ("all",):
        return ALL_REPORTS
    selected: list[str] = []
    for name in reports:
        if name == "all":
            return ALL_REPORTS
        if name not in ALL_REPORTS:
            raise ValueError(f"Unknown Shopify report '{name}'. Choose from: {', '.join(ALL_REPORTS)}")
        selected.append(name)
    return tuple(selected)


def _site_raw_dir(output_dir: Path | None, site_cfg: ShopifySiteConfig, report_name: str) -> Path:
    folder = _report_folder(report_name)
    if output_dir is not None:
        return output_dir / site_cfg.label / folder
    raw_root, _ = ensure_data_dirs("shopify", site_cfg.label)
    return raw_root / folder


def _report_folder(report_name: str) -> str:
    return {
        REPORT_SALES_ATTRIBUTION: "sales_attribution",
        REPORT_CJ_SHOPIFY: "cj_shopify",
        REPORT_IMPACT_SHOPIFY: "impact_shopify",
        REPORT_AWIN_SHOPIFY: "awin_shopify",
    }[report_name]


def _report_filename(report_name: str, period_label: str) -> str:
    return f"{_report_folder(report_name)}_{period_label}.json"


def _report_from_path(raw_path: Path) -> str:
    name = raw_path.stem
    if name.startswith("sales_attribution"):
        return REPORT_SALES_ATTRIBUTION
    if name.startswith("cj_shopify"):
        return REPORT_CJ_SHOPIFY
    if name.startswith("impact_shopify"):
        return REPORT_IMPACT_SHOPIFY
    if name.startswith("awin_shopify"):
        return REPORT_AWIN_SHOPIFY
    return REPORT_SALES_ATTRIBUTION


def _write_rows(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
