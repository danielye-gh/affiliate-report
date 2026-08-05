from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from affiliate_report.config import RAW_DIR

# shopify是否退款 values (only set when Shopify match succeeds):
#   "0" = no refund, "1" = full refund, "2" = partial refund
REFUND_NONE = "0"
REFUND_FULL = "1"
REFUND_PARTIAL = "2"
REFUND_STATUSES = frozenset({REFUND_FULL, REFUND_PARTIAL})


def is_shopify_refunded(value: object) -> bool:
    """True when shopify是否退款 is full (1) or partial (2)."""
    return str(value or "").strip() in REFUND_STATUSES


def _parse_money(value: object) -> Decimal:
    text = str(value or "").strip().replace(",", "").replace("$", "")
    if not text or text.lower() in {"nan", "none", "n/a"}:
        return Decimal("0")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def classify_refund_status(order_net_sales: Decimal, refund_amount: Decimal) -> str:
    """Classify refund using remaining order net sales vs refunded total.

    Shopify ``currentSubtotalPriceSet`` is post-refund, so remaining ≈ 0 means full.
    """
    if refund_amount <= 0:
        return REFUND_NONE
    if order_net_sales <= 0:
        return REFUND_FULL
    return REFUND_PARTIAL


def format_refund_amount(amount: Decimal) -> str:
    if amount <= 0:
        return ""
    return format(amount, ".2f")


@dataclass(frozen=True)
class ShopifyOrderIdMatch:
    order_id: str
    oid: str
    utm_source: str | None
    has_refund: bool
    discount_code: str = ""
    refund_amount: Decimal = Decimal("0")
    refund_status: str = REFUND_NONE

    def matches_utm_source(self, expected: str) -> bool:
        return (self.utm_source or "").strip().lower() == expected.strip().lower()

    @property
    def refund_amount_cell(self) -> str:
        return format_refund_amount(self.refund_amount)


@dataclass(frozen=True)
class ShopifyOidMatch:
    oid: str
    order_id: str
    utm_source: str | None
    has_refund: bool
    discount_code: str = ""
    refund_amount: Decimal = Decimal("0")
    refund_status: str = REFUND_NONE

    def matches_utm_source(self, expected: str) -> bool:
        return (self.utm_source or "").strip().lower() == expected.strip().lower()

    @property
    def refund_amount_cell(self) -> str:
        return format_refund_amount(self.refund_amount)


def _row_discount_code(row: dict) -> str:
    return str(row.get("discountCode") or "").strip()


def load_shopify_oid_index(raw_path: Path) -> dict[str, ShopifyOidMatch]:
    """Index Shopify sales-attribution rows by OID (order name without #)."""
    with raw_path.open(encoding="utf-8") as f:
        rows = json.load(f)

    orders: dict[str, dict] = {}
    refund_totals: dict[str, Decimal] = {}

    for row in rows:
        oid = str(row.get("oid") or "").strip()
        if not oid:
            continue

        row_kind = str(row.get("rowKind") or "order").strip().lower()
        if row_kind == "refund":
            refund_totals[oid] = refund_totals.get(oid, Decimal("0")) + abs(_parse_money(row.get("netSales")))
            continue

        if row_kind != "order":
            continue

        orders[oid] = {
            "order_id": str(row.get("orderId") or "").strip(),
            "utm_source": row.get("orderUtmSource"),
            "discount_code": _row_discount_code(row),
            "net_sales": _parse_money(row.get("netSales")),
        }

    index: dict[str, ShopifyOidMatch] = {}
    for oid, info in orders.items():
        order_id = info["order_id"]
        if not order_id:
            continue
        refund_amount = refund_totals.get(oid, Decimal("0"))
        refund_status = classify_refund_status(info["net_sales"], refund_amount)
        index[oid] = ShopifyOidMatch(
            oid=oid,
            order_id=order_id,
            utm_source=info["utm_source"],
            has_refund=refund_status in REFUND_STATUSES,
            discount_code=info["discount_code"],
            refund_amount=refund_amount,
            refund_status=refund_status,
        )

    return index


def load_shopify_order_id_index(raw_path: Path) -> dict[str, ShopifyOrderIdMatch]:
    """Index Shopify sales-attribution rows by Shopify orderId."""
    with raw_path.open(encoding="utf-8") as f:
        rows = json.load(f)

    orders: dict[str, dict] = {}
    refund_totals: dict[str, Decimal] = {}

    for row in rows:
        order_id = str(row.get("orderId") or "").strip()
        oid = str(row.get("oid") or "").strip()
        if not order_id:
            continue

        row_kind = str(row.get("rowKind") or "order").strip().lower()
        if row_kind == "refund":
            refund_totals[order_id] = refund_totals.get(order_id, Decimal("0")) + abs(
                _parse_money(row.get("netSales"))
            )
            continue

        if row_kind != "order":
            continue

        orders[order_id] = {
            "oid": oid,
            "utm_source": row.get("orderUtmSource"),
            "discount_code": _row_discount_code(row),
            "net_sales": _parse_money(row.get("netSales")),
        }

    index: dict[str, ShopifyOrderIdMatch] = {}
    for order_id, info in orders.items():
        refund_amount = refund_totals.get(order_id, Decimal("0"))
        refund_status = classify_refund_status(info["net_sales"], refund_amount)
        index[order_id] = ShopifyOrderIdMatch(
            order_id=order_id,
            oid=info["oid"],
            utm_source=info["utm_source"],
            has_refund=refund_status in REFUND_STATUSES,
            discount_code=info["discount_code"],
            refund_amount=refund_amount,
            refund_status=refund_status,
        )

    return index

def default_shopify_sales_attribution_path(period_label: str, *, site: str = "us") -> Path:
    return (
        RAW_DIR
        / "shopify"
        / site
        / "sales_attribution"
        / f"sales_attribution_{period_label}.json"
    )


SHOPIFY_SITES = ("us", "uk", "de")


def resolve_shopify_site_from_order_key(order_key: str) -> str:
    """Route Shopify sales-attribution lookup by order/OID prefix."""
    text = str(order_key or "").strip()
    if text.startswith(("2022", "2220")):
        return "uk"
    if text.startswith(("2023", "2320")):
        return "de"
    return "us"


def load_shopify_oid_indexes_for_period(
    period_label: str,
    *,
    sites: tuple[str, ...] = SHOPIFY_SITES,
) -> dict[str, dict[str, ShopifyOidMatch]]:
    indexes: dict[str, dict[str, ShopifyOidMatch]] = {}
    for site in sites:
        path = default_shopify_sales_attribution_path(period_label, site=site)
        if path.is_file():
            indexes[site] = load_shopify_oid_index(path)
    return indexes


def load_oid_indexes_for_process(
    period_label: str,
    *,
    shopify_path: Path | None = None,
    shopify_site: str = "all",
) -> dict[str, dict[str, ShopifyOidMatch]]:
    if shopify_path is not None:
        site = "us" if shopify_site == "all" else shopify_site
        return {site: load_shopify_oid_index(shopify_path)}

    indexes = load_shopify_oid_indexes_for_period(
        period_label,
        sites=_sites_to_load(shopify_site),
    )
    if not indexes:
        sites = ", ".join(_sites_to_load(shopify_site))
        raise FileNotFoundError(
            f"No Shopify sales attribution files found for period {period_label} ({sites})"
        )
    return indexes


def lookup_oid_match(
    oid: str,
    indexes_by_site: dict[str, dict[str, ShopifyOidMatch]],
) -> ShopifyOidMatch | None:
    text = str(oid or "").strip()
    if not text:
        return None

    site = resolve_shopify_site_from_order_key(text)
    index = indexes_by_site.get(site)
    if index is None:
        return None
    return index.get(text)


def load_shopify_order_id_indexes_for_period(
    period_label: str,
    *,
    sites: tuple[str, ...] = SHOPIFY_SITES,
) -> dict[str, dict[str, ShopifyOrderIdMatch]]:
    indexes: dict[str, dict[str, ShopifyOrderIdMatch]] = {}
    for site in sites:
        path = default_shopify_sales_attribution_path(period_label, site=site)
        if path.is_file():
            indexes[site] = load_shopify_order_id_index(path)
    return indexes


def lookup_order_id_match(
    order_id: str,
    indexes_by_site: dict[str, dict[str, ShopifyOrderIdMatch]],
) -> ShopifyOrderIdMatch | None:
    text = str(order_id or "").strip()
    if not text:
        return None

    for index in indexes_by_site.values():
        match = index.get(text)
        if match is not None:
            return match
    return None


def _sites_to_load(shopify_site: str) -> tuple[str, ...]:
    return SHOPIFY_SITES if shopify_site == "all" else (shopify_site,)


def load_order_id_indexes_for_process(
    period_label: str,
    *,
    shopify_path: Path | None = None,
    shopify_site: str = "all",
) -> dict[str, dict[str, ShopifyOrderIdMatch]]:
    if shopify_path is not None:
        site = "us" if shopify_site == "all" else shopify_site
        return {site: load_shopify_order_id_index(shopify_path)}

    indexes = load_shopify_order_id_indexes_for_period(
        period_label,
        sites=_sites_to_load(shopify_site),
    )
    if not indexes:
        sites = ", ".join(_sites_to_load(shopify_site))
        raise FileNotFoundError(
            f"No Shopify sales attribution files found for period {period_label} ({sites})"
        )
    return indexes
