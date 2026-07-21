from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()

FEISHU_BASE = "https://open.feishu.cn/open-apis"


@dataclass(frozen=True)
class FeishuSheetsConfig:
    app_id: str
    app_secret: str
    spreadsheet_token: str
    sheet_id: str | None = None

    @classmethod
    def from_env(cls) -> FeishuSheetsConfig:
        app_id = os.getenv("FEISHU_APP_ID", "").strip()
        app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
        if not app_id or not app_secret:
            raise ValueError(
                "Missing FEISHU_APP_ID or FEISHU_APP_SECRET in .env. "
                "Offline users can edit data/config/exclusive_codes.csv directly."
            )

        url = os.getenv("FEISHU_EXCLUSIVE_CODES_URL", "").strip()
        token = os.getenv("FEISHU_EXCLUSIVE_CODES_TOKEN", "").strip()
        if url:
            token = parse_spreadsheet_token(url)
        if not token:
            raise ValueError(
                "Set FEISHU_EXCLUSIVE_CODES_URL or FEISHU_EXCLUSIVE_CODES_TOKEN in .env"
            )

        sheet_id = os.getenv("FEISHU_EXCLUSIVE_CODES_SHEET_ID", "").strip() or None
        return cls(
            app_id=app_id,
            app_secret=app_secret,
            spreadsheet_token=token,
            sheet_id=sheet_id,
        )


def parse_spreadsheet_token(url_or_token: str) -> str:
    text = (url_or_token or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"[A-Za-z0-9_-]+", text) and "://" not in text:
        return text

    parsed = urlparse(text)
    path = parsed.path or ""
    # https://xxx.feishu.cn/sheets/shtcnXXXX
    match = re.search(r"/sheets/([A-Za-z0-9_-]+)", path)
    if match:
        return match.group(1)
    # https://xxx.feishu.cn/wiki/XXXX — wiki nodes need extra resolve; reject clearly
    if "/wiki/" in path:
        raise ValueError(
            "Wiki links are not supported yet. Open the embedded spreadsheet and "
            "copy its /sheets/... URL, or set FEISHU_EXCLUSIVE_CODES_TOKEN."
        )
    raise ValueError(f"Cannot parse Feishu spreadsheet token from: {url_or_token}")


class FeishuSheetsClient:
    """Read Feishu spreadsheet cells via OpenAPI (no lark-cli)."""

    def __init__(self, config: FeishuSheetsConfig, *, timeout: float = 60.0):
        self.config = config
        self._client = httpx.Client(timeout=timeout)
        self._tenant_token: str | None = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FeishuSheetsClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_tenant_access_token(self, *, force: bool = False) -> str:
        if self._tenant_token and not force:
            return self._tenant_token
        response = self._client.post(
            f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.config.app_id, "app_secret": self.config.app_secret},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"Feishu tenant_access_token failed: {payload}")
        token = payload.get("tenant_access_token")
        if not token:
            raise RuntimeError(f"Feishu tenant_access_token missing in response: {payload}")
        self._tenant_token = str(token)
        return self._tenant_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.get_tenant_access_token()}"}

    def list_sheets(self) -> list[dict[str, Any]]:
        token = self.config.spreadsheet_token
        response = self._client.get(
            f"{FEISHU_BASE}/sheets/v3/spreadsheets/{token}/sheets/query",
            headers=self._headers(),
        )
        if response.status_code == 404:
            # Fallback to v2 metainfo for older sheets.
            response = self._client.get(
                f"{FEISHU_BASE}/sheets/v2/spreadsheets/{token}/metainfo",
                headers=self._headers(),
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != 0:
                raise RuntimeError(f"Feishu sheet metainfo failed: {payload}")
            sheets = payload.get("data", {}).get("sheets") or []
            return list(sheets)

        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"Feishu sheet query failed: {payload}")
        sheets = payload.get("data", {}).get("sheets") or []
        return list(sheets)

    def resolve_sheet_id(self) -> str:
        if self.config.sheet_id:
            return self.config.sheet_id
        sheets = self.list_sheets()
        if not sheets:
            raise RuntimeError("Feishu spreadsheet has no sheets")
        first = sheets[0]
        sheet_id = first.get("sheet_id") or first.get("sheetId")
        if not sheet_id:
            raise RuntimeError(f"Cannot resolve sheet_id from: {first}")
        return str(sheet_id)

    def fetch_values(self, *, max_rows: int = 500) -> list[list[Any]]:
        sheet_id = self.resolve_sheet_id()
        token = self.config.spreadsheet_token
        cell_range = f"{sheet_id}!A1:Z{max_rows}"
        response = self._client.get(
            f"{FEISHU_BASE}/sheets/v2/spreadsheets/{token}/values/{cell_range}",
            headers=self._headers(),
            params={"valueRenderOption": "ToString"},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"Feishu values read failed: {payload}")
        values = payload.get("data", {}).get("valueRange", {}).get("values") or []
        return values
