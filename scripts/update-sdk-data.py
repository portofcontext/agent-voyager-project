"""Refresh the models.dev data every AVP SDK ships, before a publish: prices
and each provider's default base URL and auth header.

Fetches models.dev once with the Python SDK. Prices live in one shared file;
each SDK bundles it when built. Run from the repo root in the SDK's environment,
since the root workspace still installs the old `avp`:

    uv run --project avp-sdk/python python scripts/update-sdk-data.py
"""

from pathlib import Path

from avp.utils._models_dev import fetch_catalog
from avp.utils.endpoints import fetch_endpoints, save_endpoints
from avp.utils.pricing import fetch_prices, save_prices

AVP_SDK = Path(__file__).resolve().parent.parent / "avp-sdk"

PYTHON_DATA = AVP_SDK / "python" / "src" / "avp" / "utils" / "data"

PRICES = AVP_SDK / "data" / "avp_prices.json"

if __name__ == "__main__":
    catalog = fetch_catalog()
    prices = fetch_prices(catalog)
    endpoints = fetch_endpoints(catalog=catalog)
    save_prices(prices, PRICES)
    print(f"wrote {len(prices.models)} prices to {PRICES.relative_to(AVP_SDK.parent)}")
    save_endpoints(endpoints, PYTHON_DATA / "avp_endpoints.json")
    print(
        f"wrote {len(endpoints.providers)} endpoints to {PYTHON_DATA.relative_to(AVP_SDK.parent)}"
    )
