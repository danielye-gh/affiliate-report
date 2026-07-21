from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from affiliate_report.models import MonthRange
from affiliate_report.platforms.cj.client import CJClient
from affiliate_report.platforms.cj.config import CJAccountType, CJConfig, CJDateField

MAX_RANGE_DAYS = 31

# GraphQL fields to request (order follows CJ Commission Detail CSV export).
ADVERTISER_COMMISSION_FIELDS = """
    orderId
    commissionId
    postingDate
    eventDate
    publisherId
    publisherName
    websiteName
    advCommissionAmountUsd
    actionTrackerName
    actionType
    actionStatus
    saleAmountUsd
    orderDiscountUsd
    pubCommissionAmountUsd
    cjFeeUsd
    aid
    coupon
    newToFile
    isCrossDevice
    advertiserId
    advertiserName
    websiteId
    original
    validationStatus
    clickReferringURL
"""

PUBLISHER_COMMISSION_FIELDS = """
    orderId
    commissionId
    postingDate
    eventDate
    publisherId
    publisherName
    websiteName
    advCommissionAmountUsd
    actionTrackerName
    actionType
    actionStatus
    saleAmountUsd
    orderDiscountUsd
    pubCommissionAmountUsd
    cjFeeUsd
    aid
    coupon
    newToFile
    isCrossDevice
    advertiserId
    advertiserName
    websiteId
    original
    shopperId
    sid
    validationStatus
    clickReferringURL
"""


class CJCommissionsAPI:
    def __init__(self, client: CJClient, config: CJConfig):
        self._client = client
        self._config = config

    def list_commissions_for_month(self, month: MonthRange) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for start, end in _month_date_chunks(month):
            chunk = self._list_commissions(start, end)
            rows.extend(chunk)
        return rows

    def probe_access(self, *, company_id: str | None = None) -> dict[str, Any]:
        """Run a 1-day probe query to verify CID + account type."""
        cid = company_id or self._config.company_id
        since = "2026-01-01T00:00:00Z"
        before = "2026-01-02T00:00:00Z"
        if self._config.account_type == CJAccountType.ADVERTISER:
            data = self._query_advertiser_page(cid, since, before, since_commission_id=None)
            key = "advertiserCommissions"
        else:
            data = self._query_publisher_page(cid, since, before, since_commission_id=None)
            key = "publisherCommissions"

        payload = data.get(key, {})
        records = payload.get("records", [])
        sample_name = None
        if records:
            sample_name = records[0].get("advertiserName") or records[0].get("publisherName")

        return {
            "account_type": self._config.account_type.value,
            "company_id": cid,
            "count": payload.get("count", 0),
            "sample_name": sample_name,
        }

    def _list_commissions(self, start: date, end: date) -> list[dict[str, Any]]:
        since, before = _date_bounds(start, end, self._config.date_field)
        rows: list[dict[str, Any]] = []
        since_commission_id: str | None = None

        while True:
            if self._config.account_type == CJAccountType.ADVERTISER:
                data = self._query_advertiser_page(
                    self._config.company_id,
                    since,
                    before,
                    since_commission_id=since_commission_id,
                )
                payload = data["advertiserCommissions"]
                enrich = enrich_advertiser_record
            else:
                data = self._query_publisher_page(
                    self._config.company_id,
                    since,
                    before,
                    since_commission_id=since_commission_id,
                )
                payload = data["publisherCommissions"]
                enrich = enrich_publisher_record

            rows.extend(enrich(record) for record in payload.get("records", []))
            if payload.get("payloadComplete", True):
                break

            since_commission_id = payload.get("maxCommissionId")
            if not since_commission_id:
                break

        return rows

    def _query_advertiser_page(
        self,
        company_id: str,
        since: str,
        before: str,
        *,
        since_commission_id: str | None,
    ) -> dict[str, Any]:
        args = [
            f'forAdvertisers: ["{company_id}"]',
            f'since{_date_arg_suffix(self._config.date_field)}: "{since}"',
            f'before{_date_arg_suffix(self._config.date_field)}: "{before}"',
        ]
        if since_commission_id:
            args.append(f'sinceCommissionId: "{since_commission_id}"')
        if self._config.action_statuses:
            statuses = ", ".join(f'"{s}"' for s in self._config.action_statuses)
            args.append(f"actionStatuses: [{statuses}]")

        query = f"""
        {{
          advertiserCommissions({", ".join(args)}) {{
            count
            payloadComplete
            maxCommissionId
            records {{ {ADVERTISER_COMMISSION_FIELDS} }}
          }}
        }}
        """
        return self._client.graphql(query)

    def _query_publisher_page(
        self,
        company_id: str,
        since: str,
        before: str,
        *,
        since_commission_id: str | None,
    ) -> dict[str, Any]:
        args = [
            f'forPublishers: ["{company_id}"]',
            f'since{_date_arg_suffix(self._config.date_field)}: "{since}"',
            f'before{_date_arg_suffix(self._config.date_field)}: "{before}"',
        ]
        if since_commission_id:
            args.append(f'sinceCommissionId: "{since_commission_id}"')
        if self._config.website_id:
            args.append(f'websiteIds: ["{self._config.website_id}"]')
        if self._config.action_statuses:
            statuses = ", ".join(f'"{s}"' for s in self._config.action_statuses)
            args.append(f"actionStatuses: [{statuses}]")

        query = f"""
        {{
          publisherCommissions({", ".join(args)}) {{
            count
            payloadComplete
            maxCommissionId
            records {{ {PUBLISHER_COMMISSION_FIELDS} }}
          }}
        }}
        """
        return self._client.graphql(query)


def enrich_advertiser_record(record: dict[str, Any]) -> dict[str, Any]:
    """Shape API record to match CJ Commission Detail CSV column order/names."""
    return {
        "orderId": record.get("orderId"),
        "commissionId": record.get("commissionId"),
        "postingDate": record.get("postingDate"),
        "eventDate": record.get("eventDate"),
        "publisherId": record.get("publisherId"),
        "publisherName": record.get("publisherName"),
        "websiteName": record.get("websiteName"),
        "advertiserCommissionUsd": record.get("advCommissionAmountUsd"),
        "actionTrackerName": record.get("actionTrackerName"),
        "actionType": record.get("actionType"),
        "status": record.get("actionStatus"),
        "saleAmountUsd": record.get("saleAmountUsd"),
        "correctedAmountUsd": _corrected_amount_usd(record),
        "orderDiscountUsd": record.get("orderDiscountUsd"),
        "pubCommissionAmountUsd": record.get("pubCommissionAmountUsd"),
        "cjFeeUsd": record.get("cjFeeUsd"),
        "linkId": record.get("aid"),
        "coupon": record.get("coupon"),
        "newToFile": record.get("newToFile"),
        "isCrossDevice": record.get("isCrossDevice"),
        "advertiserId": record.get("advertiserId"),
        "advertiserName": record.get("advertiserName"),
        "websiteId": record.get("websiteId"),
        "original": record.get("original"),
        "validationStatus": record.get("validationStatus"),
        "clickReferringURL": record.get("clickReferringURL"),
    }


def enrich_publisher_record(record: dict[str, Any]) -> dict[str, Any]:
    enriched = enrich_advertiser_record(record)
    enriched["shopperId"] = record.get("shopperId")
    enriched["sid"] = record.get("sid")
    return enriched


def _corrected_amount_usd(record: dict[str, Any]) -> str:
    """CJ UI 'Corrected Amount (USD)' — derived when original is a correction row."""
    if record.get("original", True):
        return "0"
    adv = record.get("advCommissionAmountUsd")
    if adv is None:
        return "0"
    try:
        return str(abs(Decimal(str(adv))))
    except InvalidOperation:
        return "0"


def _date_arg_suffix(date_field: CJDateField) -> str:
    return "PostingDate" if date_field == CJDateField.POSTING else "EventDate"


def _date_bounds(start: date, end: date, date_field: CJDateField) -> tuple[str, str]:
    # CJ end bound is exclusive; use day after `end` at midnight UTC.
    since = f"{start.isoformat()}T00:00:00Z"
    before_date = end + timedelta(days=1)
    before = f"{before_date.isoformat()}T00:00:00Z"
    return since, before


def _month_date_chunks(month: MonthRange) -> list[tuple[date, date]]:
    start = month.start
    end = month.end
    if (end - start).days + 1 <= MAX_RANGE_DAYS:
        return [(start, end)]

    chunks: list[tuple[date, date]] = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=MAX_RANGE_DAYS - 1), end)
        chunks.append((chunk_start, chunk_end))
        chunk_start = chunk_end + timedelta(days=1)
    return chunks
