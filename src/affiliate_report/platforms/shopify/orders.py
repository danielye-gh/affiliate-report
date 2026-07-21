from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from affiliate_report.models import MonthRange
from affiliate_report.platforms.shopify.client import ShopifyClient
from affiliate_report.platforms.shopify.config import ShopifyConfig, UtmSourceFilter

ORDERS_QUERY = """
query OrdersForMonth($query: String!, $cursor: String) {
  orders(first: 100, after: $cursor, query: $query, sortKey: CREATED_AT) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        legacyResourceId
        name
        createdAt
        currentSubtotalPriceSet {
          shopMoney { amount currencyCode }
        }
        totalShippingPriceSet {
          shopMoney { amount }
        }
        discountCodes
        customerJourneySummary {
          lastVisit {
            utmParameters { source medium campaign }
          }
          firstVisit {
            utmParameters { source medium campaign }
          }
        }
        refunds {
          createdAt
          totalRefundedSet {
            shopMoney { amount }
          }
        }
      }
    }
  }
}
"""

# Extra calendar days on each side of the target month when querying Shopify.
# Covers orders that fall on adjacent dates due to store vs platform timezone drift.
FETCH_DAY_PADDING = 1


class ShopifyOrdersAPI:
    def __init__(self, client: ShopifyClient, config: ShopifyConfig):
        self._client = client
        self._config = config
        self._shop_timezone: ZoneInfo | None = None

    def list_attribution_rows_for_month(self, month: MonthRange) -> list[dict[str, Any]]:
        shop_tz = self._shop_timezone_zone()
        orders = self._list_orders(month)
        rows: list[dict[str, Any]] = []
        for order in orders:
            rows.extend(_order_to_attribution_rows(order, shop_tz))
        return rows

    def _shop_timezone_zone(self) -> ZoneInfo:
        if self._shop_timezone is not None:
            return self._shop_timezone
        if self._client.site.timezone:
            self._shop_timezone = ZoneInfo(self._client.site.timezone)
        else:
            self._shop_timezone = ZoneInfo(self._client.get_shop_iana_timezone())
        return self._shop_timezone

    def filter_rows(
        self,
        rows: list[dict[str, Any]],
        utm_filter: UtmSourceFilter | None,
    ) -> list[dict[str, Any]]:
        if utm_filter is None:
            return list(rows)
        return [
            row
            for row in rows
            if utm_filter.matches(row.get("orderUtmSource"))
        ]

    def _list_orders(self, month: MonthRange) -> list[dict[str, Any]]:
        start_iso, end_exclusive_iso = _orders_fetch_range(month)
        # Inclusive start, exclusive end (Shopify search syntax).
        query = f"created_at:>={start_iso} created_at:<{end_exclusive_iso}"
        orders: list[dict[str, Any]] = []
        cursor: str | None = None

        while True:
            data = self._client.graphql(
                ORDERS_QUERY,
                variables={"query": query, "cursor": cursor},
            )
            connection = data.get("orders") or {}
            for edge in connection.get("edges", []):
                node = edge.get("node")
                if node:
                    orders.append(node)

            page_info = connection.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
            if not cursor:
                break

        return orders


def _next_month_start(month: MonthRange) -> date:
    if month.month == 12:
        return date(month.year + 1, 1, 1)
    return date(month.year, month.month + 1, 1)


def _orders_fetch_range(month: MonthRange) -> tuple[str, str]:
    pad = timedelta(days=FETCH_DAY_PADDING)
    start = month.start - pad
    end_exclusive = _next_month_start(month) + pad
    return start.isoformat(), end_exclusive.isoformat()


def _order_to_attribution_rows(order: dict[str, Any], shop_tz: ZoneInfo) -> list[dict[str, Any]]:
    utm = _extract_utm(order)
    order_id = str(order.get("legacyResourceId") or "")
    order_name = str(order.get("name") or "")
    oid = order_name.lstrip("#") if order_name.startswith("#") else order_id
    discount_code = _format_discount_codes(order.get("discountCodes"))

    net_sales = _money_amount(order.get("currentSubtotalPriceSet"))
    shipping = _money_amount(order.get("totalShippingPriceSet"))
    created_at = order.get("createdAt")

    rows = [
        _attribution_row(
            utm=utm,
            order_id=order_id,
            oid=oid,
            order_name=order_name,
            discount_code=discount_code,
            event_at=created_at,
            net_sales=net_sales,
            shipping_charges=shipping,
            row_kind="order",
            shop_tz=shop_tz,
        )
    ]

    for refund in order.get("refunds") or []:
        refund_amount = _money_amount(refund.get("totalRefundedSet"))
        if refund_amount is None or refund_amount == 0:
            continue
        rows.append(
            _attribution_row(
                utm=utm,
                order_id=order_id,
                oid=oid,
                order_name=order_name,
                discount_code=discount_code,
                event_at=refund.get("createdAt") or created_at,
                net_sales=-abs(refund_amount),
                shipping_charges=Decimal("0"),
                row_kind="refund",
                shop_tz=shop_tz,
            )
        )

    return rows


def _attribution_row(
    *,
    utm: dict[str, str | None],
    order_id: str,
    oid: str,
    order_name: str,
    discount_code: str,
    event_at: str | None,
    net_sales: Decimal | None,
    shipping_charges: Decimal | None,
    row_kind: str,
    shop_tz: ZoneInfo,
) -> dict[str, Any]:
    sales = net_sales or Decimal("0")
    return {
        "orderUtmSource": utm.get("source"),
        "orderUtmMedium": utm.get("medium"),
        "orderUtmCampaign": utm.get("campaign"),
        "orderId": order_id,
        "oid": oid,
        "orderName": order_name,
        "discountCode": discount_code,
        "minute": _format_minute(event_at, shop_tz),
        "netSales": _decimal_str(sales),
        "shippingCharges": _decimal_str(shipping_charges or Decimal("0")),
        "orders": 0 if sales == 0 else 1,
        "rowKind": row_kind,
        "eventAt": event_at,
    }


def _format_discount_codes(raw: object) -> str:
    """Join Shopify order discountCodes into a single comma-separated string."""
    if raw is None:
        return ""
    codes: list[str] = []
    if isinstance(raw, str):
        text = raw.strip()
        return text
    if isinstance(raw, list):
        for item in raw:
            if item is None:
                continue
            if isinstance(item, dict):
                text = str(item.get("code") or item.get("title") or "").strip()
            else:
                text = str(item).strip()
            if text and text not in codes:
                codes.append(text)
    return ",".join(codes)


def _extract_utm(order: dict[str, Any]) -> dict[str, str | None]:
    journey = order.get("customerJourneySummary") or {}
    for visit_key in ("lastVisit", "firstVisit"):
        visit = journey.get(visit_key) or {}
        params = visit.get("utmParameters") or {}
        if any(params.get(k) for k in ("source", "medium", "campaign")):
            return {
                "source": params.get("source"),
                "medium": params.get("medium"),
                "campaign": params.get("campaign"),
            }
    return {"source": None, "medium": None, "campaign": None}


def _money_amount(money_set: dict[str, Any] | None) -> Decimal | None:
    if not money_set:
        return None
    shop_money = money_set.get("shopMoney") or {}
    return _to_decimal(shop_money.get("amount"))


def _to_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _decimal_str(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _format_minute(value: str | None, shop_tz: ZoneInfo) -> str | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(shop_tz)
        return f"{local.year}/{local.month}/{local.day} {local.hour}:{local.minute:02d}"
    except ValueError:
        return value
