"""Refresh the models.dev price snapshot every AVP SDK ships, before a publish.

Fetches once with the Python SDK and writes the same file into each SDK, since
each package must carry its own copy. Run from the repo root in the SDK's
environment, since the root workspace still installs the old `avp`:

    uv run --project avp_sdk/python python scripts/update-prices.py
"""

from pathlib import Path

from avp.utils.pricing import fetch_prices, save_prices

AVP_SDK = Path(__file__).resolve().parent.parent / "avp_sdk"

# Add the Rust and TypeScript SDKs' copies here when they exist.
SNAPSHOTS = [AVP_SDK / "python" / "src" / "avp" / "utils" / "data" / "avp_prices.json"]

if __name__ == "__main__":
    prices = fetch_prices()
    for snapshot in SNAPSHOTS:
        save_prices(prices, snapshot)
        print(f"wrote {len(prices.models)} models to {snapshot.relative_to(AVP_SDK.parent)}")
