from affiliate_report.exclusive_codes.store import (
    EXCLUSIVE_CODES_CSV,
    ensure_exclusive_codes_csv,
    load_exclusive_code_rules,
)


def apply_exclusive_code_action_rules(*args, **kwargs):
    from affiliate_report.exclusive_codes.rules import apply_exclusive_code_action_rules as _apply

    return _apply(*args, **kwargs)


def sync_exclusive_codes_from_feishu(*args, **kwargs):
    from affiliate_report.exclusive_codes.sync import sync_exclusive_codes_from_feishu as _sync

    return _sync(*args, **kwargs)


__all__ = [
    "EXCLUSIVE_CODES_CSV",
    "apply_exclusive_code_action_rules",
    "ensure_exclusive_codes_csv",
    "load_exclusive_code_rules",
    "sync_exclusive_codes_from_feishu",
]
