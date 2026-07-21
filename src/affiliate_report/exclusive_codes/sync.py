from __future__ import annotations

from pathlib import Path
from typing import Any

from affiliate_report.exclusive_codes.feishu import FeishuSheetsClient, FeishuSheetsConfig
from affiliate_report.exclusive_codes.store import (
    EXCLUSIVE_CODES_CSV,
    normalize_code_match,
    parse_code_list,
    write_exclusive_codes_csv,
)


_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "partner": (
        "partner",
        "媒体",
        "媒体名称",
        "partner name",
        "publisher",
        "publisher name",
    ),
    "publisher_id": (
        "publisher_id",
        "publisher id",
        "partner id",
        "partner_id",
        "id",
        "媒体id",
        "媒体 id",
    ),
    "exclusive_codes": (
        "exclusive_codes",
        "exclusive code",
        "exclusive codes",
        "独家code",
        "独家code (不区分大小写)",
        "独家Code",
        "独家Code (不区分大小写)",
        "独家码",
        "优惠码",
    ),
    "code_match": (
        "code_match",
        "match_mode",
        "匹配方式",
        "code match",
    ),
    "enabled": (
        "enabled",
        "启用",
        "是否启用",
    ),
    "note": (
        "note",
        "备注",
        "说明",
    ),
}


def _normalize_header(value: object) -> str:
    text = str(value or "").strip().casefold()
    text = text.replace("\n", " ").replace("\r", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts = [_cell_text(item) for item in value]
        return "".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("text", "name", "value", "link"):
            if key in value and value[key] is not None:
                return str(value[key]).strip()
        return str(value).strip()
    return str(value).strip()


def _map_headers(header_row: list[Any]) -> dict[str, int]:
    normalized = [_normalize_header(cell) for cell in header_row]
    mapping: dict[str, int] = {}
    for field, aliases in _HEADER_ALIASES.items():
        alias_set = {_normalize_header(alias) for alias in aliases}
        for idx, header in enumerate(normalized):
            if header in alias_set:
                mapping[field] = idx
                break
    if "partner" not in mapping:
        raise ValueError(
            "Feishu sheet missing partner/媒体 column. "
            f"Headers found: {[_cell_text(c) for c in header_row]}"
        )
    return mapping


def rows_from_sheet_values(values: list[list[Any]]) -> list[dict[str, str]]:
    if not values:
        return []
    mapping = _map_headers(values[0])
    rows: list[dict[str, str]] = []
    for raw in values[1:]:
        if not raw:
            continue
        partner = _cell_text(raw[mapping["partner"]]) if mapping["partner"] < len(raw) else ""
        if not partner:
            continue

        def _get(field: str) -> str:
            idx = mapping.get(field)
            if idx is None or idx >= len(raw):
                return ""
            return _cell_text(raw[idx])

        codes_raw = _get("exclusive_codes")
        note = _get("note")
        codes = parse_code_list(codes_raw)
        # Prefer explicit note; fall back to detecting "开头" in the code cell itself.
        match_hint = note or codes_raw
        code_match = normalize_code_match(_get("code_match"), codes=codes, note=match_hint)
        enabled = _get("enabled") or "true"
        rows.append(
            {
                "partner": partner,
                "publisher_id": _get("publisher_id"),
                "exclusive_codes": ",".join(codes),
                "code_match": code_match,
                "enabled": enabled,
                "note": note,
            }
        )
    return rows


def sync_exclusive_codes_from_feishu(
    *,
    output_path: Path | None = None,
    config: FeishuSheetsConfig | None = None,
) -> Path:
    """Pull Feishu sheet and overwrite local exclusive_codes.csv."""
    cfg = config or FeishuSheetsConfig.from_env()
    target = output_path or EXCLUSIVE_CODES_CSV
    with FeishuSheetsClient(cfg) as client:
        values = client.fetch_values()
    rows = rows_from_sheet_values(values)
    if not rows:
        raise RuntimeError("Feishu sheet has no data rows under the header")
    return write_exclusive_codes_csv(rows, target)
