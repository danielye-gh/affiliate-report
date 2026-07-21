from __future__ import annotations

import sys
from typing import Any

import httpx

from affiliate_report.platforms.shopify.config import ShopifySiteConfig, normalize_shop_domain


class ShopifyAPIError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


SHOP_TIMEZONE_QUERY = """
{
  shop { ianaTimezone }
}
"""


class ShopifyClient:
    """Low-level HTTP client for Shopify Admin GraphQL API."""

    def __init__(
        self,
        site: ShopifySiteConfig,
        *,
        api_version: str = "2025-01",
        timeout: float = 120.0,
        verbose: bool = False,
    ):
        self.site = site
        self.api_version = api_version
        self.verbose = verbose
        host = normalize_shop_domain(site.shop)
        self._url = f"https://{host}/admin/api/{api_version}/graphql.json"
        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": site.access_token,
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ShopifyClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def graphql(self, query: str, *, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        print(f">>> POST {self._url}", file=sys.stderr, flush=True)
        response = self._client.post(self._url, json=payload)
        if self.verbose:
            print(f"<<< {response.status_code} POST {self._url}", file=sys.stderr, flush=True)

        body = _safe_json(response)
        if response.status_code >= 400:
            raise ShopifyAPIError(
                f"Shopify GraphQL failed: {response.status_code}",
                status_code=response.status_code,
                body=body,
            )

        if isinstance(body, dict) and body.get("errors"):
            message = "; ".join(
                str(err.get("message", err)) for err in body["errors"] if isinstance(err, dict)
            )
            raise ShopifyAPIError(message or "Shopify GraphQL returned errors", body=body)

        if not isinstance(body, dict) or "data" not in body:
            raise ShopifyAPIError("Unexpected Shopify GraphQL response", body=body)

        return body["data"]

    def get_shop_iana_timezone(self) -> str:
        data = self.graphql(SHOP_TIMEZONE_QUERY)
        shop = data.get("shop") or {}
        iana = shop.get("ianaTimezone")
        if not iana:
            raise ShopifyAPIError("Shopify shop timezone not available", body=data)
        return str(iana)


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text[:500]
