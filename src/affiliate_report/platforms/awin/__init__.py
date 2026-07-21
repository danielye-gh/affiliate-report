from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from affiliate_report.base.client import AffiliatePlatformClient
from affiliate_report.config import ensure_data_dirs
from affiliate_report.models import MonthRange
from affiliate_report.platforms.awin.client import AwinClient
from affiliate_report.platforms.awin.config import AwinConfig, AwinSiteConfig
from affiliate_report.platforms.awin.publishers import (
    PUBLISHERS_FILENAME,
    write_publishers,
)
from affiliate_report.platforms.awin.publishers import AwinPublishersAPI
from affiliate_report.platforms.awin.transactions import AwinTransactionsAPI
from affiliate_report.preprocess.awin import preprocess_awin_actions


class AwinPlatformClient(AffiliatePlatformClient):
    platform_name = "awin"

    def __init__(self, config: AwinConfig | None = None, *, verbose: bool | None = None):
        self.config = config or AwinConfig.from_env()
        self.verbose = self.config.verbose if verbose is None else verbose

    def _http_client(self) -> AwinClient:
        return AwinClient(self.config.api_token, verbose=self.verbose)

    def fetch_monthly_actions(
        self,
        month: MonthRange,
        *,
        output_dir: Path | None = None,
        site: str | None = None,
    ) -> Path:
        paths = self.fetch_monthly_actions_by_site(month, site=site, output_dir=output_dir)
        if len(paths) == 1:
            return next(iter(paths.values()))
        raw_root = output_dir or ensure_data_dirs(self.platform_name)[0]
        return raw_root

    def fetch_monthly_actions_by_site(
        self,
        month: MonthRange,
        *,
        site: str | None = None,
        output_dir: Path | None = None,
    ) -> dict[str, Path]:
        site_configs = self.config.resolve_sites(site)
        results: dict[str, Path] = {}

        with self._http_client() as http:
            transactions_api = AwinTransactionsAPI(http)
            publishers_api = AwinPublishersAPI(http)
            for site_cfg in site_configs:
                raw_dir = _site_raw_dir(output_dir, site_cfg)
                raw_dir.mkdir(parents=True, exist_ok=True)
                out_path = raw_dir / f"actions_{month.label}.json"
                transactions = transactions_api.list_transactions_for_month(site_cfg, month)
                _write_transactions(out_path, transactions)
                publishers = publishers_api.list_publishers(site_cfg)
                write_publishers(raw_dir / PUBLISHERS_FILENAME, publishers)
                results[site_cfg.label] = out_path

        return results

    def preprocess_actions(
        self,
        raw_path: Path,
        month: MonthRange,
        *,
        site: str | None = None,
    ) -> pd.DataFrame:
        site_label = site or raw_path.parent.name
        return preprocess_awin_actions(raw_path, month.label, site=site_label)

    def fetch_and_preprocess(
        self,
        month: MonthRange,
        *,
        site: str | None = None,
    ) -> tuple[dict[str, Path], dict[str, Path]]:
        raw_paths = self.fetch_monthly_actions_by_site(month, site=site)
        processed_paths: dict[str, Path] = {}

        for site_label, raw_path in raw_paths.items():
            df = self.preprocess_actions(raw_path, month, site=site_label)
            _, processed_dir = ensure_data_dirs(self.platform_name, site_label)
            processed_path = processed_dir / f"actions_{month.label}.parquet"
            df.to_parquet(processed_path, index=False)
            processed_paths[site_label] = processed_path

        return raw_paths, processed_paths

    def list_accounts(self) -> list[dict]:
        with self._http_client() as http:
            payload = http.get_json("/accounts")
        accounts = payload.get("accounts", []) if isinstance(payload, dict) else []
        return accounts if isinstance(accounts, list) else []


def _site_raw_dir(output_dir: Path | None, site_cfg: AwinSiteConfig) -> Path:
    if output_dir is not None:
        return output_dir / site_cfg.label
    raw_root, _ = ensure_data_dirs("awin", site_cfg.label)
    return raw_root


def _write_transactions(path: Path, transactions: list[dict]) -> None:
    path.write_text(json.dumps(transactions, ensure_ascii=False, indent=2), encoding="utf-8")
