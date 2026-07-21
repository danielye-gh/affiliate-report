from __future__ import annotations

from typing import Any, Iterator

from affiliate_report.models import MonthRange
from affiliate_report.platforms.impact.client import ImpactClient


class ImpactActionsAPI:
    """Impact Actions endpoint — filter by EventDate (ActionDateStart/End)."""

    def __init__(self, client: ImpactClient):
        self._client = client

    def list_actions_for_month(
        self,
        month: MonthRange,
        *,
        campaign_id: int | str | None = None,
        state: str | None = None,
        page_size: int = 2000,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "ActionDateStart": month.action_date_start,
            "ActionDateEnd": month.action_date_end,
            "PageSize": max(page_size, 2000),
        }
        if campaign_id is not None:
            params["CampaignId"] = campaign_id
        if state:
            params["State"] = state

        return list(self._iter_actions(params))

    def list_actions_for_advertiser_month(
        self,
        month: MonthRange,
        *,
        campaign_ids: list[int | str] | None = None,
        state: str | None = None,
    ) -> list[dict[str, Any]]:
        """Advertiser Actions API requires CampaignId — fetch one or all campaigns."""
        if campaign_ids is None:
            payload = self._client.get_json(self._client._path("/Campaigns"))
            campaign_ids = [c["Id"] for c in payload.get("Campaigns") or []]

        if not campaign_ids:
            raise ValueError("No campaigns found for this advertiser account")

        all_actions: list[dict[str, Any]] = []
        for campaign_id in campaign_ids:
            all_actions.extend(
                self.list_actions_for_month(month, campaign_id=campaign_id, state=state)
            )
        return all_actions

    def _iter_actions(self, params: dict[str, Any]) -> Iterator[dict[str, Any]]:
        path = self._client._path("/Actions")
        page = 1

        while True:
            page_params = {**params, "Page": page}
            payload = self._client.get_json(path, params=page_params)
            actions = payload.get("Actions") or []
            yield from actions

            if not actions:
                break
            if len(actions) < params.get("PageSize", 2000):
                break
            page += 1

            # Safety: Impact caps at 10 pages for some queries
            if page > 10:
                break
