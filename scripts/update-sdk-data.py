"""Refresh the models.dev data every AVP SDK ships, before a publish: prices
and default base URLs.

Fetches models.dev once with the Python SDK and writes the same files into each
SDK, since each package must carry its own copy. Run from the repo root in the
SDK's environment, since the root workspace still installs the old `avp`:

    uv run --project avp_sdk/python python scripts/update-sdk-data.py
"""

from pathlib import Path

from avp.utils._models_dev import fetch_catalog
from avp.utils.base_urls import fetch_base_urls, save_base_urls
from avp.utils.pricing import fetch_prices, save_prices

AVP_SDK = Path(__file__).resolve().parent.parent / "avp_sdk"

# Each SDK's data directory. Add the Rust and TypeScript SDKs' when they exist.
DATA_DIRS = [AVP_SDK / "python" / "src" / "avp" / "utils" / "data"]

if __name__ == "__main__":
    catalog = fetch_catalog()
    prices = fetch_prices(catalog)
    base_urls = fetch_base_urls(catalog=catalog)
    for data in DATA_DIRS:
        where = data.relative_to(AVP_SDK.parent)
        save_prices(prices, data / "avp_prices.json")
        save_base_urls(base_urls, data / "avp_base_urls.json")
        print(
            f"wrote {len(prices.models)} prices and {len(base_urls.providers)} base URLs to {where}"
        )
