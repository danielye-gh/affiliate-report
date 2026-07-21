from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from affiliate_report.platforms.awin.client import AwinClient
from affiliate_report.platforms.awin.config import AwinSiteConfig

PUBLISHERS_FILENAME = "publishers.json"


class AwinPublishersAPI:
    def __init__(self, client: AwinClient):
        self._client = client

    def list_publishers(self, site: AwinSiteConfig) -> list[dict[str, Any]]:
        path = f"/advertisers/{site.advertiser_id}/publishers"
        payload = self._client.get_json(path)
        if not isinstance(payload, list):
            raise ValueError(f"Unexpected Awin publishers response for {site.label}: {payload!r}")
        return payload


def default_publishers_path(site_label: str, *, raw_root: Path | None = None) -> Path:
    if raw_root is not None:
        return raw_root / site_label / PUBLISHERS_FILENAME
    from affiliate_report.config import RAW_DIR

    return RAW_DIR / "awin" / site_label / PUBLISHERS_FILENAME


def write_publishers(path: Path, publishers: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(publishers, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_publishers(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as f:
        payload = json.load(f)
    return payload if isinstance(payload, list) else []


def build_publisher_name_index(publishers: list[dict[str, Any]]) -> dict[str, str]:
    index: dict[str, str] = {}
    for row in publishers:
        publisher_id = str(row.get("id", "")).strip()
        name = str(row.get("name", "")).strip()
        if publisher_id and name:
            index[publisher_id] = name
    return index


def resolve_publisher_name(publisher_id: object, name_index: dict[str, str]) -> str:
    key = str(publisher_id or "").strip()
    if not key:
        return ""
    return name_index.get(key, key)
