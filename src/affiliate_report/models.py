from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any


@dataclass
class ActionRecord:
    """Cross-platform normalized action (conversion) record."""

    platform: str
    action_id: str
    order_id: str | None
    event_date: datetime | None
    state: str | None
    revenue: Decimal | None
    commission: Decimal | None
    currency: str | None
    campaign_id: str | None = None
    campaign_name: str | None = None
    partner_id: str | None = None
    partner_name: str | None = None
    event_type: str | None = None
    sub_id_1: str | None = None
    sub_id_2: str | None = None
    sub_id_3: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class MonthRange:
    year: int
    month: int

    @property
    def label(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def start(self) -> date:
        return date(self.year, self.month, 1)

    @property
    def end(self) -> date:
        if self.month == 12:
            next_month = date(self.year + 1, 1, 1)
        else:
            next_month = date(self.year, self.month + 1, 1)
        from datetime import timedelta

        return next_month - timedelta(days=1)

    @property
    def start_iso(self) -> str:
        return self.start.isoformat()

    @property
    def end_iso(self) -> str:
        return self.end.isoformat()

    @property
    def action_date_start(self) -> str:
        return f"{self.start_iso}T00:00:00Z"

    @property
    def action_date_end(self) -> str:
        return f"{self.end_iso}T23:59:59Z"
