from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from affiliate_report.config import RAW_DIR


@dataclass(frozen=True)
class ShopifyOrderIdMatch:
    order_id: str
    oid: str
    utm_source: str | None
    has_refund: bool
    discount_code: str = ""

    def matches_utm_source(self, expected: str) -> bool:
        return (self.utm_source or "").strip().lower() == expected.strip().lower()


@dataclass(frozen=True)
class ShopifyOidMatch:
    oid: str
    order_id: str
    utm_source: str | None
    has_refund: bool
    discount_code: str = ""

    def matches_utm_source(self, expected: str) -> bool:
        return (self.utm_source or "").strip().lower() == expected.strip().lower()


def _row_discount_code(row: dict) -> str:
    return str(row.get("discountCode") or "").strip()


def load_shopify_oid_index(raw_path: Path) -> dict[str, ShopifyOidMatch]:
    """Index Shopify sales-attribution rows by OID (order name without #)."""
    with raw_path.open(encoding="utf-8") as f:
        rows = json.load(f)

    orders: dict[str, dict] = {}
    refunds: set[str] = set()

    for row in rows:
        oid = str(row.get("oid") or "").strip()
        if not oid:
            continue

        row_kind = str(row.get("rowKind") or "order").strip().lower()
        if row_kind == "refund":
            refunds.add(oid)
            continue

        if row_kind != "order":
            continue

        orders[oid] = {
            "order_id": str(row.get("orderId") or "").strip(),
            "utm_source": row.get("orderUtmSource"),
            "discount_code": _row_discount_code(row),
        }

    index: dict[str, ShopifyOidMatch] = {}
    for oid, info in orders.items():
        order_id = info["order_id"]
        if not order_id:
            continue
        index[oid] = ShopifyOidMatch(
            oid=oid,
            order_id=order_id,
            utm_source=info["utm_source"],
            has_refund=oid in refunds,
            discount_code=info["discount_code"],
        )

    return index


def load_shopify_order_id_index(raw_path: Path) -> dict[str, ShopifyOrderIdMatch]:
    """Index Shopify sales-attribution rows by Shopify orderId."""
    with raw_path.open(encoding="utf-8") as f:
        rows = json.load(f)

    orders: dict[str, dict] = {}
    refunds: set[str] = set()

    for row in rows:
        order_id = str(row.get("orderId") or "").strip()
        oid = str(row.get("oid") or "").strip()
        if not order_id:
            continue

        row_kind = str(row.get("rowKind") or "order").strip().lower()
        if row_kind == "refund":
            refunds.add(order_id)
            continue

        if row_kind != "order":
            continue

        orders[order_id] = {
            "oid": oid,
            "utm_source": row.get("orderUtmSource"),
            "discount_code": _row_discount_code(row),
        }

    index: dict[str, ShopifyOrderIdMatch] = {}
    for order_id, info in orders.items():
        index[order_id] = ShopifyOrderIdMatch(
            order_id=order_id,
            oid=info["oid"],
            utm_source=info["utm_source"],
            has_refund=order_id in refunds,
            discount_code=info["discount_code"],
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
