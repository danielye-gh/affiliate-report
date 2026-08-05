from __future__ import annotations

from decimal import Decimal

import pandas as pd

from affiliate_report.reconcile.formatting import parse_commission
from affiliate_report.reconcile.shopify import is_shopify_refunded

ACTION_PASS = "通过"
ACTION_CANCEL = "取消"


def normalize_partner_name(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "n/a"}:
        return ""
    return text


def apply_partner_volume_action_rules(
    df: pd.DataFrame,
    *,
    partner_column: str,
    commission_column: str,
    refund_column: str = "shopify是否退款",
    action_column: str = "Action",
) -> pd.DataFrame:
    """Apply small-volume partner pass rules on unresolved Action rows.

    - Total ≤ 2: pass all unresolved rows (except refunded + positive commission)
    - 2 < Total ≤ 5: top up passes to ≥50%, preferring low commission
    - Total > 5: unchanged

    Never overrides existing 通过 / 取消 from higher-priority rules.
    """
    if df.empty or partner_column not in df.columns or action_column not in df.columns:
        return df

    result = df.copy()
    partner_keys = result[partner_column].map(normalize_partner_name)
    counts = partner_keys.value_counts()

    for partner, total in counts.items():
        if total > 5:
            continue
        group_mask = partner_keys == partner
        if total <= 2:
            _apply_small_partner_rule(
                result,
                group_mask,
                commission_column=commission_column,
                refund_column=refund_column,
                action_column=action_column,
            )
        else:
            _apply_medium_partner_rule(
                result,
                group_mask,
                commission_column=commission_column,
                refund_column=refund_column,
                action_column=action_column,
                total=total,
            )

    return result


def _apply_small_partner_rule(
    df: pd.DataFrame,
    group_mask: pd.Series,
    *,
    commission_column: str,
    refund_column: str,
    action_column: str,
) -> None:
    for idx in df.index[group_mask]:
        if str(df.at[idx, action_column] or "").strip() != "":
            continue
        if _is_refund_with_positive_commission(
            df.loc[idx], commission_column=commission_column, refund_column=refund_column
        ):
            continue
        df.at[idx, action_column] = ACTION_PASS


def _apply_medium_partner_rule(
    df: pd.DataFrame,
    group_mask: pd.Series,
    *,
    commission_column: str,
    refund_column: str,
    action_column: str,
    total: int,
) -> None:
    group = df.loc[group_mask]
    required_passes = (total + 1) // 2
    current_passes = int((group[action_column] == ACTION_PASS).sum())
    needed = max(0, required_passes - current_passes)
    if needed == 0:
        return

    # Prefer unresolved rows; skip refunded + positive commission.
    candidates = group[group[action_column].map(lambda v: str(v or "").strip() == "")]
    eligible_idx = [
        idx
        for idx in candidates.index
        if not _is_refund_with_positive_commission(
            df.loc[idx], commission_column=commission_column, refund_column=refund_column
        )
    ]
    if not eligible_idx:
        return

    commission_values = {
        idx: parse_commission(df.at[idx, commission_column]) if commission_column in df.columns else Decimal("0")
        for idx in eligible_idx
    }
    selected = sorted(eligible_idx, key=lambda idx: (commission_values[idx], idx))[:needed]
    for idx in selected:
        df.at[idx, action_column] = ACTION_PASS


def _is_refund_with_positive_commission(
    row: pd.Series,
    *,
    commission_column: str,
    refund_column: str,
) -> bool:
    if refund_column not in row.index or not is_shopify_refunded(row[refund_column]):
        return False
    if commission_column not in row.index:
        return False
    return parse_commission(row[commission_column]) > 0
