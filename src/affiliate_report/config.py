from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from affiliate_report.impact_filters import ImpactReportFilters

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
CONFIG_DIR = DATA_DIR / "config"
REPORTS_DIR = DATA_DIR / "reports"


@dataclass(frozen=True)
class ImpactConfig:
    account_sid: str
    auth_token: str
    account_type: str = "advertiser"
    program_id: str | None = None
    action_report_handle: str | None = None
    report_filters: ImpactReportFilters | None = None
    verbose: bool = False

    @classmethod
    def from_env(cls) -> ImpactConfig:
        account_sid = os.getenv("IMPACT_ACCOUNT_SID", "").strip()
        auth_token = os.getenv("IMPACT_AUTH_TOKEN", "").strip()
        if not account_sid or not auth_token:
            raise ValueError(
                "Missing IMPACT_ACCOUNT_SID or IMPACT_AUTH_TOKEN in environment / .env"
            )
        account_type = os.getenv("IMPACT_ACCOUNT_TYPE", "advertiser").strip().lower()
        if account_type not in {"advertiser", "mediapartner"}:
            raise ValueError("IMPACT_ACCOUNT_TYPE must be 'advertiser' or 'mediapartner'")
        program_id = os.getenv("IMPACT_PROGRAM_ID", "").strip() or None
        report_handle = os.getenv("IMPACT_ACTION_REPORT_HANDLE", "").strip() or None
        verbose = os.getenv("IMPACT_DEBUG", "").strip().lower() in {"1", "true", "yes"}
        return cls(
            account_sid=account_sid,
            auth_token=auth_token,
            account_type=account_type,
            program_id=program_id,
            action_report_handle=report_handle,
            report_filters=ImpactReportFilters.from_env(),
            verbose=verbose,
        )


def ensure_data_dirs(platform: str, site: str | None = None) -> tuple[Path, Path]:
    raw = RAW_DIR / platform
    processed = PROCESSED_DIR / platform
    if site:
        raw = raw / site
        processed = processed / site
    raw.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    return raw, processed
