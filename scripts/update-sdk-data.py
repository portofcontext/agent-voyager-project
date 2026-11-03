"""Refresh the models.dev data every AVP SDK ships, before a publish: prices
and each provider's default base URL and auth header.

Fetches models.dev once with the Python SDK. Data lives in one shared directory;
each SDK bundles it when built. Run from the repo root in the SDK's environment,
since the root workspace still installs the old `avp`:

    uv run --project avp-sdk/python python scripts/update-sdk-data.py
"""

from sdk_data import DATA, SDK, sync_links

from avp.utils._models_dev import fetch_catalog
from avp.utils.endpoints import fetch_endpoints, save_endpoints
from avp.utils.pricing import fetch_prices, save_prices

if __name__ == "__main__":
    catalog = fetch_catalog()
    prices = fetch_prices(catalog)
    endpoints = fetch_endpoints(catalog=catalog)
    save_prices(prices, DATA / "avp_prices.json")
    save_endpoints(endpoints, DATA / "avp_endpoints.json")
    sync_links()
    print(
        f"wrote {len(prices.models)} prices and {len(endpoints.providers)} endpoints to "
        f"{DATA.relative_to(SDK.parent)}"
    )
