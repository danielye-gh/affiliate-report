from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pandas as pd

from affiliate_report.base.client import AffiliatePlatformClient
from affiliate_report.config import ImpactConfig, ensure_data_dirs
from affiliate_report.models import MonthRange
from affiliate_report.platforms.impact.actions import ImpactActionsAPI
from affiliate_report.platforms.impact.client import ImpactClient
from affiliate_report.impact_filters import ImpactReportFilters, apply_filters_to_csv
from affiliate_report.platforms.impact.actions_supplement import (
    supplement_csv_with_missing_action_statuses,
)
from affiliate_report.platforms.impact.reports import ImpactReportsAPI
from affiliate_report.preprocess.impact import preprocess_impact_actions


class ImpactPlatformClient(AffiliatePlatformClient):
    platform_name = "impact"

    def __init__(self, config: ImpactConfig | None = None, *, verbose: bool | None = None):
        self.config = config or ImpactConfig.from_env()
        self.verbose = self.config.verbose if verbose is None else verbose

    def _http_client(self) -> ImpactClient:
        return ImpactClient(
            self.config.account_sid,
            self.config.auth_token,
            account_type=self.config.account_type,
            verbose=self.verbose,
        )

    def fetch_monthly_actions(
        self,
        month: MonthRange,
        *,
        output_dir: Path | None = None,
        method: str = "report",
        report_handle: str | None = None,
    ) -> Path:
        raw_dir = output_dir or ensure_data_dirs(self.platform_name)[0]
        raw_dir.mkdir(parents=True, exist_ok=True)
        out_path = raw_dir / f"actions_{month.label}.csv"

        with self._http_client() as http:
            if method == "actions":
                path = self._fetch_via_actions_api(http, month, out_path)
            elif method == "report-sync":
                path = self._fetch_via_report_sync(
                    http, month, out_path, report_handle=report_handle
                )
            elif method == "report":
                path = self._fetch_via_report_export(
                    http, month, out_path, report_handle=report_handle
                )
            else:
                raise ValueError("method must be 'report', 'report-sync', or 'actions'")
        return path

    def preprocess_actions(self, raw_path: Path, month: MonthRange) -> pd.DataFrame:
        return preprocess_impact_actions(raw_path, month.label)

    def list_reports(self) -> list[dict]:
        with self._http_client() as http:
            return ImpactReportsAPI(http).list_api_accessible_reports()

    def _fetch_via_report_sync(
        self,
        http: ImpactClient,
        month: MonthRange,
        out_path: Path,
        *,
        report_handle: str | None,
    ) -> Path:
        handle = report_handle or self.config.action_report_handle
        if not handle:
            handle = self._guess_action_report_handle(http)

        reports = ImpactReportsAPI(http)
        filter_params = (self.config.report_filters or ImpactReportFilters()).to_api_params()
        csv_bytes = reports.run_report_sync_csv(
            handle,
            month,
            program_id=self.config.program_id,
            extra_params=filter_params,
        )
        filters = self.config.report_filters or ImpactReportFilters()
        if filters.action_statuses:
            csv_bytes = supplement_csv_with_missing_action_statuses(
                csv_bytes,
                filters,
                http=http,
                month=month,
                program_id=self.config.program_id,
            )
        csv_bytes = apply_filters_to_csv(csv_bytes, filters)
        out_path.write_bytes(csv_bytes)
        return out_path

    def _fetch_via_report_export(
        self,
        http: ImpactClient,
        month: MonthRange,
        out_path: Path,
        *,
        report_handle: str | None,
    ) -> Path:
        handle = report_handle or self.config.action_report_handle
        if not handle:
            handle = self._guess_action_report_handle(http)

        reports = ImpactReportsAPI(http)
        filters = self.config.report_filters or ImpactReportFilters()
        csv_bytes = reports.export_report_csv(
            handle,
            month,
            program_id=self.config.program_id,
            extra_params=filters.to_api_params(),
        )
        if filters.action_statuses:
            csv_bytes = supplement_csv_with_missing_action_statuses(
                csv_bytes,
                filters,
                http=http,
                month=month,
                program_id=self.config.program_id,
            )
        csv_bytes = apply_filters_to_csv(csv_bytes, filters)
        out_path.write_bytes(csv_bytes)
        return out_path

    def _fetch_via_actions_api(
        self,
        http: ImpactClient,
        month: MonthRange,
        out_path: Path,
    ) -> Path:
        actions_api = ImpactActionsAPI(http)
        if http.account_type == "advertiser":
            campaign_ids = [self.config.program_id] if self.config.program_id else None
            actions = actions_api.list_actions_for_advertiser_month(
                month, campaign_ids=campaign_ids
            )
        else:
            campaign_id = int(self.config.program_id) if self.config.program_id else None
            actions = actions_api.list_actions_for_month(month, campaign_id=campaign_id)

        if not actions:
            out_path.write_text("", encoding="utf-8")
            return out_path

        fieldnames = sorted({key for row in actions for key in row})
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(actions)
        return out_path

    def _guess_action_report_handle(self, http: ImpactClient) -> str:
        reports = ImpactReportsAPI(http).list_api_accessible_reports()
        keywords = ("action", "listing", "transaction")
        candidates = [
            r
            for r in reports
            if any(k in (r.get("Id") or "").lower() or k in (r.get("Name") or "").lower() for k in keywords)
        ]
        if not candidates:
            names = ", ".join(r.get("Id", "?") for r in reports[:10])
            raise ValueError(
                "Set IMPACT_ACTION_REPORT_HANDLE in .env. "
                f"Available API reports (first 10): {names}"
            )
        preferred = next(
            (r["Id"] for r in candidates if "listing" in (r.get("Id") or "").lower()),
            candidates[0]["Id"],
        )
        return preferred

    def fetch_and_preprocess(
        self,
        month: MonthRange,
        *,
        method: str = "report",
        report_handle: str | None = None,
    ) -> tuple[Path, Path]:
        raw_path = self.fetch_monthly_actions(
            month, method=method, report_handle=report_handle
        )
        df = self.preprocess_actions(raw_path, month)
        _, processed_dir = ensure_data_dirs(self.platform_name)
        processed_path = processed_dir / f"actions_{month.label}.parquet"
        df.to_parquet(processed_path, index=False)
        return raw_path, processed_path

    @staticmethod
    def actions_to_dataframe(actions: list[dict]) -> pd.DataFrame:
        return pd.json_normalize(actions) if actions else pd.DataFrame()

    @staticmethod
    def csv_bytes_to_preview(csv_bytes: bytes, rows: int = 3) -> str:
        text = csv_bytes.decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text))
        lines = []
        for i, row in enumerate(reader):
            if i > rows:
                break
            lines.append(",".join(row))
        return "\n".join(lines)
