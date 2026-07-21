from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from dotenv import load_dotenv

load_dotenv()


class CJAccountType(str, Enum):
    ADVERTISER = "advertiser"
    PUBLISHER = "publisher"


class CJDateField(str, Enum):
    POSTING = "posting"
    EVENT = "event"


@dataclass(frozen=True)
class CJConfig:
    api_token: str
    account_type: CJAccountType
    company_id: str
    website_id: str | None = None
    date_field: CJDateField = CJDateField.POSTING
    action_statuses: tuple[str, ...] = ()
    verbose: bool = False

    @classmethod
    def from_env(cls, *, require_company_id: bool = True) -> CJConfig:
        api_token = os.getenv("CJ_API_KEY", "").strip()
        if not api_token:
            raise ValueError("Missing CJ_API_KEY in environment / .env")

        company_id = (
            os.getenv("CJ_COMPANY_ID", "").strip()
            or os.getenv("CJ_ADVERTISER_ID", "").strip()
            or os.getenv("CJ_PUBLISHER_ID", "").strip()
        )
        if require_company_id and not company_id:
            raise ValueError(
                "Missing CJ_COMPANY_ID in environment / .env "
                "(aliases: CJ_ADVERTISER_ID, CJ_PUBLISHER_ID). "
                "Find your CID in CJ dashboard → Account."
            )

        account_type = _read_account_type()
        website_id = os.getenv("CJ_WEBSITE_ID", "").strip() or None
        date_field = _read_date_field()
        action_statuses = _read_action_statuses()
        verbose = os.getenv("CJ_DEBUG", "").strip().lower() in {"1", "true", "yes"}

        return cls(
            api_token=api_token,
            account_type=account_type,
            company_id=company_id,
            website_id=website_id,
            date_field=date_field,
            action_statuses=action_statuses,
            verbose=verbose,
        )


def _read_account_type() -> CJAccountType:
    raw = os.getenv("CJ_ACCOUNT_TYPE", "advertiser").strip().lower()
    if raw in {"advertiser", "adv", "brand"}:
        return CJAccountType.ADVERTISER
    if raw in {"publisher", "pub", "partner"}:
        return CJAccountType.PUBLISHER
    raise ValueError("CJ_ACCOUNT_TYPE must be 'advertiser' or 'publisher'")


def _read_date_field() -> CJDateField:
    raw = os.getenv("CJ_DATE_FIELD", "posting").strip().lower()
    if raw in {"posting", "post"}:
        return CJDateField.POSTING
    if raw in {"event", "transaction"}:
        return CJDateField.EVENT
    raise ValueError("CJ_DATE_FIELD must be 'posting' or 'event'")


def _read_action_statuses() -> tuple[str, ...]:
    raw = os.getenv("CJ_ACTION_STATUS", "").strip()
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())
