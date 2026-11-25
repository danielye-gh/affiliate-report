"""Read order-level attribution from DTC; never use database sales as order totals."""
from __future__ import annotations

import os
import ssl
from dataclasses import dataclass, field
from typing import Iterable

import pymysql

from affiliate_report.config import PROJECT_ROOT
from affiliate_report.shopify_attribution import read_order_utm_source
from dotenv import load_dotenv

TABLE = "dwd_wb_shopify_orders_original_sku_detail_di"
STORE_NAMES = {
    "us": "PETLIBRO", "uk": "PETLIBRO UK", "de": "PETLIBRO DE",
    "fr": "PETLIBRO FR", "au": "PETLIBRO AU",
}


@dataclass(frozen=True)
class DtcAttribution:
    source: str
    order_id: str
    oid: str


@dataclass
class DtcIndex:
    by_oid: dict[tuple[str, str], DtcAttribution] = field(default_factory=dict)
    by_order_id: dict[tuple[str, str], DtcAttribution] = field(default_factory=dict)


def supplement_shopify_rows(
    rows: list[dict], *, site: str, index: DtcIndex | None = None,
) -> list[dict]:
    """Enrich the full Shopify set before any affiliate filtering, preserving events."""
    for row in rows:
        read_order_utm_source(row)
    if index is None:
        index = load_attribution({site: [r.get("orderId") or "" for r in rows]}, key_type="order_id")
    result = []
    for row in rows:
        match = index.by_order_id.get((STORE_NAMES[site], str(row.get("orderId") or "").strip()))
        result.append({**row, "补充归因": match.source if match else ""})
    return result


def select_shopify_affiliate_rows(
    rows: list[dict], source: str, *, original_source: str | None = None,
) -> list[dict]:
    """Keep the union of original and supplementary attribution, once per input event."""
    expected = source.strip().lower()
    original = (original_source or os.getenv(f"SHOPIFY_{expected.upper()}_UTM_SOURCE") or expected).strip().lower()
    return [row for row in rows if (
        (read_order_utm_source(row) or "").lower() == original
        or str(row.get("补充归因") or "").strip().lower() == expected
    )]


def build_index(rows: Iterable[dict]) -> DtcIndex:
    """Select the latest snapshot before checking its eligibility as a supplement."""
    latest: dict[tuple[str, str], tuple[tuple[str, ...], dict[str, DtcAttribution]]] = {}
    for row in rows:
        source = str(row.get("last_visit_utm_source") or "").strip().lower()
        store = str(row["store_name"]).strip()
        order_id = str(row["order_id"]).strip()
        oid = str(row.get("order_name") or "").strip().lstrip("#")
        rank = tuple(str(row.get(k) or "") for k in ("_etl_loaded_at", "sale_happened_at", "order_updated_date"))
        key = (store, order_id)
        match = DtcAttribution(source, order_id, oid)
        if key not in latest or rank > latest[key][0]:
            latest[key] = (rank, {source: match})
        elif rank == latest[key][0]:
            latest[key][1][source] = match
    result = DtcIndex()
    for (store, order_id), (_, sources) in latest.items():
        if len(sources) != 1:
            raise ValueError(f"DTC attribution conflict for {store} order {order_id}")
        match = next(iter(sources.values()))
        if match.source not in {"impact", "awin"}:
            continue
        result.by_order_id[store, order_id] = match
        if match.oid:
            key = (store, match.oid)
            if key in result.by_oid and result.by_oid[key] != match:
                raise ValueError(f"DTC duplicate order name for {store}: {match.oid}")
            result.by_oid[key] = match
    return result


def load_attribution(keys_by_site: dict[str, Iterable[str]], *, key_type: str) -> DtcIndex:
    """Query report orders, with no sales-date cutoff (old orders may be amended)."""
    if key_type not in {"oid", "order_id"}:
        raise ValueError("Invalid DTC order key type")
    requests = []
    for site, values in keys_by_site.items():
        store = STORE_NAMES[site]
        keys = sorted({str(v).strip().lstrip("#") for v in values if str(v).strip()})
        if keys:
            requests.append((store, keys))
    if not requests:
        return DtcIndex()
    load_dotenv(PROJECT_ROOT / ".env")
    user = os.getenv("DTC_DATABASE_USER", "")
    password = os.getenv("DTC_DATABASE_PASSWORD", "")
    if not user or not password:
        raise ValueError("Missing DTC_DATABASE_USER or DTC_DATABASE_PASSWORD in .env")
    rows = []
    try:
        with pymysql.connect(
            host=os.getenv("DTC_DATABASE_HOST", "gateway01.us-east-1.prod.aws.tidbcloud.com"),
            port=int(os.getenv("DTC_DATABASE_PORT", "4000")),
            database=os.getenv("DTC_DATABASE_NAME", "dtc"),
            user=user, password=password, ssl=ssl.create_default_context(),
            connect_timeout=15, read_timeout=90, write_timeout=15,
            cursorclass=pymysql.cursors.DictCursor,
        ) as db, db.cursor() as cur:
            cur.execute("SET SESSION MAX_EXECUTION_TIME=60000")
            for store, keys in requests:
                for start in range(0, len(keys), 500):
                    batch = keys[start:start + 500]
                    if key_type == "oid":
                        # Both forms cover stores whose displayed order names omit #.
                        batch = [name for key in batch for name in ("#" + key, key)]
                    column = "order_name" if key_type == "oid" else "order_id"
                    placeholders = ",".join(["%s"] * len(batch))
                    cur.execute(
                        f"SELECT store_name, order_id, order_name, last_visit_utm_source, "
                        f"_etl_loaded_at, sale_happened_at, order_updated_date FROM `{TABLE}` "
                        f"WHERE store_name=%s AND `{column}` IN ({placeholders})",
                        [store, *batch],
                    )
                    rows.extend(cur.fetchall())
    except pymysql.MySQLError:
        # Server errors may include the login name: do not propagate credentials to GUI/logs.
        raise RuntimeError("DTC database query failed; check connection, access and .env configuration") from None
    return build_index(rows)
