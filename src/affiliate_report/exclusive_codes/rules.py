from __future__ import annotations

import pandas as pd

from affiliate_report.exclusive_codes.store import (
    ExclusiveCodeRule,
    load_exclusive_code_rules,
    normalize_id,
    normalize_name,
)

ACTION_PASS = "通过"


def promo_uses_exclusive_code(promo: object, rule: ExclusiveCodeRule) -> bool:
    text = str(promo or "").strip()
    if not text or text.lower() in {"nan", "none", "n/a"}:
        return False
    if rule.code_match == "none" or not rule.codes:
        return False

    # Shopify may return multiple discount codes joined by commas.
    candidates = [
        part.strip()
        for part in text.replace("；", ",").replace(";", ",").split(",")
        if part.strip()
    ] or [text]

    for candidate in candidates:
        key = candidate.casefold()
        if rule.code_match == "prefix":
            if any(key.startswith(code.casefold()) for code in rule.codes):
                return True
        elif any(key == code.casefold() for code in rule.codes):
            return True
    return False


def find_matching_rule(
    *,
    partner: object,
    publisher_id: object,
    rules: list[ExclusiveCodeRule],
) -> ExclusiveCodeRule | None:
    partner_key = normalize_name(partner)
    publisher_key = normalize_id(publisher_id)

    if publisher_key:
        for rule in rules:
            if publisher_key in rule.publisher_ids:
                return rule

    if not partner_key:
        return None
    for rule in rules:
        if rule.partner_key == partner_key:
            return rule
    return None


def apply_exclusive_code_action_rules(
    df: pd.DataFrame,
    *,
    partner_column: str,
    promo_column: str,
    publisher_id_column: str | None = None,
    match_column: str = "匹配情况",
    refund_column: str = "shopify是否退款",
    action_column: str = "Action",
    match_value: str = "匹配",
    rules: list[ExclusiveCodeRule] | None = None,
) -> pd.DataFrame:
    """Pass unresolved rows that used a configured exclusive discount code.

    Only partners listed in exclusive_codes.csv are considered. Does not cancel
    other rows (finalize step handles remaining empties). Never overrides 取消.

    ``match_column`` / ``refund_column`` / ``match_value`` are retained for
    call-site compatibility; match/refund passes are handled earlier.
    """
    _ = (match_column, refund_column, match_value)

    if df.empty or action_column not in df.columns:
        return df
    if partner_column not in df.columns:
        return df

    active_rules = rules if rules is not None else load_exclusive_code_rules()
    if not active_rules:
        return df

    result = df.copy()
    for idx in result.index:
        row = result.loc[idx]
        if str(row.get(action_column, "")).strip() != "":
            continue

        publisher_id = row[publisher_id_column] if publisher_id_column and publisher_id_column in result.columns else ""
        rule = find_matching_rule(
            partner=row[partner_column],
            publisher_id=publisher_id,
            rules=active_rules,
        )
        if rule is None:
            continue

        promo = row[promo_column] if promo_column in result.columns else ""
        if promo_uses_exclusive_code(promo, rule):
            result.at[idx, action_column] = ACTION_PASS

    return result
