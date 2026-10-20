"""CJ platform client.

Currently disabled in monthly report / CLI (search ``CJ disabled`` to re-enable).
This module is kept intact for a future restart.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from affiliate_report.base.client import AffiliatePlatformClient
from affiliate_report.config import ensure_data_dirs
from affiliate_report.models import MonthRange
from affiliate_report.platforms.cj.client import CJClient
from affiliate_report.platforms.cj.commissions import CJCommissionsAPI
from affiliate_report.platforms.cj.config import CJConfig
from affiliate_report.preprocess.cj import preprocess_cj_actions


class CJPlatformClient(AffiliatePlatformClient):
    platform_name = "cj"

    def __init__(self, config: CJConfig | None = None, *, verbose: bool | None = None):
        self.config = config or CJConfig.from_env()
        self.verbose = self.config.verbose if verbose is None else verbose

    def _http_client(self) -> CJClient:
        return CJClient(self.config.api_token, verbose=self.verbose)

    def fetch_monthly_actions(
        self,
        month: MonthRange,
        *,
        output_dir: Path | None = None,
    ) -> Path:
        raw_dir = output_dir or ensure_data_dirs(self.platform_name)[0]
        raw_dir.mkdir(parents=True, exist_ok=True)
        out_path = raw_dir / f"actions_{month.label}.json"

        with self._http_client() as http:
            api = CJCommissionsAPI(http, self.config)
            commissions = api.list_commissions_for_month(month)

        out_path.write_text(
            json.dumps(commissions, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return out_path

    def preprocess_actions(self, raw_path: Path, month: MonthRange) -> pd.DataFrame:
        return preprocess_cj_actions(raw_path, month.label)

    def fetch_and_preprocess(self, month: MonthRange) -> tuple[Path, Path]:
        raw_path = self.fetch_monthly_actions(month)
        df = self.preprocess_actions(raw_path, month)
        _, processed_dir = ensure_data_dirs(self.platform_name)
        processed_path = processed_dir / f"actions_{month.label}.parquet"
        df.to_parquet(processed_path, index=False)
        return raw_path, processed_path

    def probe_access(self, *, company_id: str | None = None) -> dict:
        with self._http_client() as http:
            return CJCommissionsAPI(http, self.config).probe_access(company_id=company_id)
