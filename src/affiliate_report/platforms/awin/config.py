from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from dotenv import load_dotenv

load_dotenv()


class AwinSite(str, Enum):
    DE = "de"
    UK = "uk"


@dataclass(frozen=True)
class AwinSiteConfig:
    site: AwinSite
    advertiser_id: int
    timezone: str
    account_name: str | None = None

    @property
    def label(self) -> str:
        return self.site.value


@dataclass(frozen=True)
class AwinConfig:
    api_token: str
    sites: tuple[AwinSiteConfig, ...]
    verbose: bool = False

    @classmethod
    def from_env(cls) -> AwinConfig:
        api_token = os.getenv("AWIN_API_TOKEN", "").strip()
        if not api_token:
            raise ValueError("Missing AWIN_API_TOKEN in environment / .env")

        sites: list[AwinSiteConfig] = []
        for site, env_key, tz in (
            (AwinSite.DE, "AWIN_ADVERTISER_ID_DE", "Europe/Berlin"),
            (AwinSite.UK, "AWIN_ADVERTISER_ID_UK", "Europe/London"),
        ):
            advertiser_id = _read_advertiser_id(site, env_key)
            if advertiser_id:
                sites.append(
                    AwinSiteConfig(
                        site=site,
                        advertiser_id=advertiser_id,
                        timezone=tz,
                    )
                )

        if not sites:
            raise ValueError(
                "Configure at least one Awin site: "
                "AWIN_ADVERTISER_ID_DE and/or AWIN_ADVERTISER_ID_UK "
                "(legacy aliases: AWIN_PUBLISHER_ID_DE / AWIN_PUBLISHER_ID_UK)"
            )

        verbose = os.getenv("AWIN_DEBUG", "").strip().lower() in {"1", "true", "yes"}
        return cls(api_token=api_token, sites=tuple(sites), verbose=verbose)

    def site_config(self, site: AwinSite | str) -> AwinSiteConfig:
        key = site.value if isinstance(site, AwinSite) else site.lower()
        for cfg in self.sites:
            if cfg.label == key:
                return cfg
        available = ", ".join(s.label for s in self.sites)
        raise ValueError(f"Unknown or unconfigured Awin site '{site}'. Available: {available}")

    def resolve_sites(self, site: str | None) -> tuple[AwinSiteConfig, ...]:
        if not site or site.lower() == "all":
            return self.sites
        return (self.site_config(site),)


def _read_advertiser_id(site: AwinSite, primary_env: str) -> int | None:
    legacy_env = f"AWIN_PUBLISHER_ID_{site.value.upper()}"
    raw = os.getenv(primary_env, "").strip() or os.getenv(legacy_env, "").strip()
    if not raw:
        return None
    return int(raw)
