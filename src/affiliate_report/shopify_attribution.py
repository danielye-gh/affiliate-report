"""Canonical Shopify last-visit attribution schema shared by every report path."""
from __future__ import annotations


def read_order_utm_source(row: dict) -> str | None:
    if "order_utm_source" not in row:
        raise ValueError(
            "Shopify 数据缺少 order_utm_source，可能是包含首次访问回退的旧版缓存。"
            "请重新拉取 Shopify 数据（fetch shopify --report all），不要使用旧缓存生成报表。"
        )
    value = row["order_utm_source"]
    return str(value).strip() if value is not None else None
