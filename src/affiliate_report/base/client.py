from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

from affiliate_report.models import MonthRange


class AffiliatePlatformClient(ABC):
    """Base contract for affiliate network API clients."""

    platform_name: str

    @abstractmethod
    def fetch_monthly_actions(
        self,
        month: MonthRange,
        *,
        output_dir: Path | None = None,
    ) -> Path:
        """Fetch raw monthly actions report and return path to saved file."""

    @abstractmethod
    def preprocess_actions(self, raw_path: Path, month: MonthRange) -> pd.DataFrame:
        """Convert platform-specific raw export to normalized dataframe."""
