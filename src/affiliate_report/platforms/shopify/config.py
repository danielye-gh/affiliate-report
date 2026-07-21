from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from dotenv import load_dotenv

load_dotenv()


class ShopifySite(str, Enum):
    US = "us"
    DE = "de"
    UK = "uk"


@dataclass(frozen=True)
class UtmSourceFilter:
    """Filter orders by UTM source only (cj / impact / awin)."""

    source: str

    def matches(self, utm_source: str | None) -> bool:
        return (utm_source or "").strip().lower() == self.source.strip().lower()


@dataclass(frozen=True)
class ShopifySiteConfig:
    site: ShopifySite
    shop: str
    access_token: str
    timezone: str | None = None

    @property
    def label(self) -> str:
        return self.site.value

    @property
    def host(self) -> str:
        return normalize_shop_domain(self.shop)


@dataclass(frozen=True)
class ShopifyConfig:
    sites: tuple[ShopifySiteConfig, ...]
    api_version: str = "2025-01"
    cj_utm_source: str = "cj"
    impact_utm_source: str = "impact"
    awin_utm_source: str = "awin"
    verbose: bool = False

    @property
    def cj_utm(self) -> UtmSourceFilter:
        return UtmSourceFilter(self.cj_utm_source)

    @property
    def impact_utm(self) -> UtmSourceFilter:
        return UtmSourceFilter(self.impact_utm_source)

    @property
    def awin_utm(self) -> UtmSourceFilter:
        return UtmSourceFilter(self.awin_utm_source)

    @classmethod
    def from_env(cls) -> ShopifyConfig:
        sites: list[ShopifySiteConfig] = []
        for site, shop_key, token_key, tz_key in (
            (
                ShopifySite.US,
                "SHOPIFY_SHOP_US",
                "SHOPIFY_ACCESS_TOKEN_US",
                "SHOPIFY_TIMEZONE_US",
            ),
            (
                ShopifySite.DE,
                "SHOPIFY_SHOP_DE",
                "SHOPIFY_ACCESS_TOKEN_DE",
                "SHOPIFY_TIMEZONE_DE",
            ),
            (
                ShopifySite.UK,
                "SHOPIFY_SHOP_UK",
                "SHOPIFY_ACCESS_TOKEN_UK",
                "SHOPIFY_TIMEZONE_UK",
            ),
        ):
            shop = os.getenv(shop_key, "").strip()
            token = os.getenv(token_key, "").strip()
            tz = os.getenv(tz_key, "").strip() or None
            if shop and token:
                sites.append(
                    ShopifySiteConfig(site=site, shop=shop, access_token=token, timezone=tz)
                )

        if not sites:
            raise ValueError(
                "Configure at least one Shopify site, e.g. "
                "SHOPIFY_SHOP_US + SHOPIFY_ACCESS_TOKEN_US"
            )

        api_version = os.getenv("SHOPIFY_API_VERSION", "2025-01").strip() or "2025-01"
        verbose = os.getenv("SHOPIFY_DEBUG", "").strip().lower() in {"1", "true", "yes"}
        return cls(
            sites=tuple(sites),
            api_version=api_version,
            cj_utm_source=os.getenv("SHOPIFY_CJ_UTM_SOURCE", "cj").strip() or "cj",
            impact_utm_source=os.getenv("SHOPIFY_IMPACT_UTM_SOURCE", "impact").strip() or "impact",
            awin_utm_source=os.getenv("SHOPIFY_AWIN_UTM_SOURCE", "awin").strip() or "awin",
            verbose=verbose,
        )

    def site_config(self, site: ShopifySite | str) -> ShopifySiteConfig:
        key = site.value if isinstance(site, ShopifySite) else site.lower()
        for cfg in self.sites:
            if cfg.label == key:
                return cfg
        available = ", ".join(s.label for s in self.sites)
        raise ValueError(f"Unknown or unconfigured Shopify site '{site}'. Available: {available}")

    def resolve_sites(self, site: str | None) -> tuple[ShopifySiteConfig, ...]:
        if not site or site.lower() == "all":
            return self.sites
        return (self.site_config(site),)


def normalize_shop_domain(shop: str) -> str:
    value = shop.strip().lower()
    value = value.removeprefix("https://").removeprefix("http://").rstrip("/")
    if "." not in value:
        value = f"{value}.myshopify.com"
    return value
