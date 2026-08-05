from __future__ import annotations

from decimal import Decimal, InvalidOperation

import pandas as pd

from affiliate_report.reconcile.shopify import is_shopify_refunded


def parse_commission(value: object) -> Decimal:
    text = str(value or "").strip().replace(",", "").replace("$", "")
    if not text or text.lower() in {"nan", "none", "n/a"}:
        return Decimal("0")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def format_decimal_cell(value: object) -> str:
    text = str(value or "").strip().replace(",", "").replace("$", "")
    if not text or text.lower() in {"nan", "none", "n/a"}:
        return ""
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return text
    return format(amount, ".2f")


def format_decimal_columns(df: pd.DataFrame, columns: tuple[str, ...] | list[str]) -> pd.DataFrame:
    result = df.copy()
    for col in columns:
        if col in result.columns:
            result[col] = result[col].map(format_decimal_cell)
    return result


def format_datetime_cell(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    dt = pd.to_datetime(text, errors="coerce", utc=True)
    if pd.isna(dt):
        return text
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_bool_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "n/a"}:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    lowered = text.lower()
    if lowered in {"true", "1", "yes"}:
        return "true"
    if lowered in {"false", "0", "no"}:
        return "false"
    return text


def is_zero_commission(value: object) -> bool:
    return parse_commission(value).is_zero()


def apply_shopify_action_column(
    df: pd.DataFrame,
    *,
    match_column: str = "匹配情况",
    action_column: str = "Action",
    refund_column: str = "shopify是否退款",
    commission_column: str | None = None,
    match_value: str = "匹配",
) -> pd.DataFrame:
    """Set base Action by priority:

    1. Commission == 0 -> 通过
    2. Commission != 0 and shopify是否退款 in {1全额, 2部分} -> 取消
    3. Matched (remaining) -> 通过
    """
    result = df.copy()
    if action_column not in result.columns:
        return result

    result[action_column] = ""

    zero_commission = pd.Series(False, index=result.index)
    if commission_column and commission_column in result.columns:
        zero_commission = result[commission_column].map(is_zero_commission)
        result.loc[zero_commission, action_column] = "通过"

    if refund_column in result.columns:
        refunded = result[refund_column].map(is_shopify_refunded)
        result.loc[refunded & ~zero_commission, action_column] = "取消"

    if match_column in result.columns:
        matched_empty = (result[action_column] == "") & (result[match_column] == match_value)
        result.loc[matched_empty, action_column] = "通过"

    return result


def finalize_action_column(
    df: pd.DataFrame,
    *,
    action_column: str = "Action",
    cancel_value: str = "取消",
) -> pd.DataFrame:
    """Cancel any rows whose Action is still unresolved."""
    result = df.copy()
    if action_column not in result.columns:
        return result
    unresolved = result[action_column].map(lambda v: str(v or "").strip() == "")
    result.loc[unresolved, action_column] = cancel_value
    return result
