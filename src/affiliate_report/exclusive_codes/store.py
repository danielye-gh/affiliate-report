from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from affiliate_report.config import DATA_DIR

CONFIG_DIR = DATA_DIR / "config"
EXCLUSIVE_CODES_CSV = CONFIG_DIR / "exclusive_codes.csv"
EXCLUSIVE_CODES_EXAMPLE_CSV = CONFIG_DIR / "exclusive_codes.example.csv"

CSV_FIELDS = (
    "partner",
    "publisher_id",
    "exclusive_codes",
    "code_match",
    "enabled",
    "note",
)

# Non-sensitive placeholders used only when the example file is missing.
_DEFAULT_ROWS: tuple[dict[str, str], ...] = (
    {
        "partner": "Example Partner",
        "publisher_id": "",
        "exclusive_codes": "EXAMPLE15,EXAMPLE20",
        "code_match": "exact",
        "enabled": "true",
        "note": "示例行：请改成真实媒体与独家 code",
    },
    {
        "partner": "Example Prefix Partner",
        "publisher_id": "",
        "exclusive_codes": "PREFIX",
        "code_match": "prefix",
        "enabled": "true",
        "note": "前缀匹配示例",
    },
)


@dataclass(frozen=True)
class ExclusiveCodeRule:
    partner: str
    publisher_ids: tuple[str, ...]
    codes: tuple[str, ...]
    code_match: str  # exact | prefix | none
    enabled: bool
    note: str = ""

    @property
    def partner_key(self) -> str:
        return normalize_name(self.partner)


def normalize_name(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "n/a", "-"}:
        return ""
    return text.casefold()


def normalize_id(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "n/a", "-"}:
        return ""
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def parse_code_list(raw: object) -> tuple[str, ...]:
    text = str(raw or "").strip()
    if not text or text in {"-", "—", "无"}:
        return ()
    # Feishu cells sometimes put "AS15开头的动态码" in the code column.
    prefix_note = re.search(r"(?i)^([A-Za-z0-9_-]+)\s*开头", text)
    if prefix_note:
        return (prefix_note.group(1),)

    parts: list[str] = []
    for chunk in text.replace("；", ",").replace(";", ",").replace("、", ",").split(","):
        code = chunk.strip()
        if code.endswith("*"):
            code = code[:-1].strip()
        if code and code not in {"-", "—"}:
            parts.append(code)
    return tuple(parts)


def parse_id_list(raw: object) -> tuple[str, ...]:
    text = str(raw or "").strip()
    if not text or text in {"-", "—"}:
        return ()
    ids: list[str] = []
    for chunk in text.replace("；", ",").replace(";", ",").split(","):
        value = normalize_id(chunk)
        if value:
            ids.append(value)
    return tuple(ids)


def parse_enabled(raw: object) -> bool:
    text = str(raw or "true").strip().lower()
    return text not in {"0", "false", "no", "n", "否", "禁用", "disabled"}


def normalize_code_match(raw: object, *, codes: tuple[str, ...], note: str = "") -> str:
    text = str(raw or "").strip().casefold()
    if text in {"exact", "精确", "全匹配", "equals"}:
        return "exact"
    if text in {"prefix", "前缀", "开头", "startswith"}:
        return "prefix"
    if text in {"none", "无", "n/a", "-"}:
        return "none"
    if "开头" in str(note or "") or "前缀" in str(note or ""):
        return "prefix" if codes else "none"
    if not codes:
        return "none"
    return "exact"


def ensure_exclusive_codes_csv(path: Path | None = None) -> Path:
    """Create local exclusive_codes.csv on first run (copy example, else placeholders)."""
    import shutil

    target = path or EXCLUSIVE_CODES_CSV
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        return target
    example = EXCLUSIVE_CODES_EXAMPLE_CSV
    if example.is_file():
        shutil.copy2(example, target)
        return target
    write_exclusive_codes_csv(_DEFAULT_ROWS, target)
    return target


def write_exclusive_codes_csv(rows: list[dict[str, str]] | tuple[dict[str, str], ...], path: Path | None = None) -> Path:
    target = path or EXCLUSIVE_CODES_CSV
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: str(row.get(field, "") or "") for field in CSV_FIELDS})
    return target


def load_exclusive_code_rules(path: Path | None = None) -> list[ExclusiveCodeRule]:
    csv_path = ensure_exclusive_codes_csv(path)
    rules: list[ExclusiveCodeRule] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            if not raw:
                continue
            partner = str(raw.get("partner") or "").strip()
            if not partner:
                continue
            codes = parse_code_list(raw.get("exclusive_codes"))
            note = str(raw.get("note") or "").strip()
            rules.append(
                ExclusiveCodeRule(
                    partner=partner,
                    publisher_ids=parse_id_list(raw.get("publisher_id")),
                    codes=codes,
                    code_match=normalize_code_match(raw.get("code_match"), codes=codes, note=note),
                    enabled=parse_enabled(raw.get("enabled")),
                    note=note,
                )
            )
    return [rule for rule in rules if rule.enabled]
