"""Check the complete shared data inventory in every SDK's published archives."""

import io
import json
import runpy
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import sdk_data
from sdk_data import DATA, PACKAGE_DATA

ROOT = Path(__file__).resolve().parent.parent


class PackagingTests(unittest.TestCase):
    def test_refresh_shares_one_catalog_and_links_every_data_file(self) -> None:
        catalog = {
            "anthropic": {
                "npm": "@ai-sdk/anthropic",
                "models": {"test": {"cost": {"input": 1, "output": 2}}},
            }
        }
        with tempfile.TemporaryDirectory() as out:
            sdk = Path(out)
            data = sdk / "data"
            data.mkdir()
            # A new shared file must be picked up without a per-language inventory edit.
            (data / "extra.json").write_text("{}\n")
            directories = {language: sdk / language / "data" for language in PACKAGE_DATA}
            with (
                patch.multiple(sdk_data, SDK=sdk, DATA=data, PACKAGE_DATA=directories),
                patch("avp.utils._models_dev.fetch_catalog", return_value=catalog) as fetch,
                redirect_stdout(io.StringIO()),
            ):
                runpy.run_path(str(ROOT / "scripts/update-sdk-data.py"), run_name="__main__")
                sdk_data.sync_links()  # Linking is idempotent.
            fetch.assert_called_once_with()
            self.assertEqual(
                json.loads((data / "avp_prices.json").read_text())["models"],
                {"anthropic/test": {"input": 1, "output": 2}},
            )
            self.assertEqual(
                json.loads((data / "avp_endpoints.json").read_text())["providers"],
                {
                    "anthropic": {
                        "base_url": "https://api.anthropic.com/v1",
                        "auth": {"header": "x-api-key", "prefix": ""},
                    }
                },
            )
            for directory in directories.values():
                self.assertEqual(
                    {path.name for path in directory.glob("*.json")},
                    {path.name for path in data.glob("*.json")},
                )
                for source in data.glob("*.json"):
                    self.assertEqual((directory / source.name).resolve(), source.resolve())

    def test_package_links_match_shared_inventory(self) -> None:
        shared = {source.name for source in DATA.glob("*.json")}
        self.assertTrue(shared)
        for language, directory in PACKAGE_DATA.items():
            with self.subTest(language=language):
                self.assertEqual({p.name for p in directory.glob("*.json")}, shared)
                for name in shared:
                    link = directory / name
                    self.assertTrue(link.is_symlink(), f"{link} must link to shared data")
                    self.assertFalse(link.readlink().is_absolute())
                    self.assertEqual(link.resolve(), (DATA / name).resolve())

    def assert_tar_data(self, archive: Path, directory: str) -> None:
        with tarfile.open(archive) as package:
            prefix = f"/{directory}/"
            self.assertEqual(
                {
                    entry.name.split(prefix, 1)[1]
                    for entry in package.getmembers()
                    if prefix in entry.name and entry.name.endswith(".json")
                },
                {source.name for source in DATA.glob("*.json")},
            )
            for source in DATA.glob("*.json"):
                with self.subTest(archive=archive.name, data=source.name):
                    suffix = f"/{directory}/{source.name}"
                    matches = [
                        entry for entry in package.getmembers() if entry.name.endswith(suffix)
                    ]
                    self.assertEqual(len(matches), 1)
                    self.assertTrue(matches[0].isfile(), "the archive must contain a regular file")
                    contents = package.extractfile(matches[0])
                    assert contents is not None
                    self.assertEqual(contents.read(), source.read_bytes())

    def test_python_wheel_and_sdist(self) -> None:
        with tempfile.TemporaryDirectory() as out:
            subprocess.run(
                ["uv", "build", "--offline", "--out-dir", out],
                cwd=ROOT / "avp-sdk" / "python",
                check=True,
                capture_output=True,
            )
            with zipfile.ZipFile(next(Path(out).glob("*.whl"))) as wheel:
                self.assertEqual(
                    {
                        name.removeprefix("avp/utils/data/")
                        for name in wheel.namelist()
                        if name.startswith("avp/utils/data/") and name.endswith(".json")
                    },
                    {source.name for source in DATA.glob("*.json")},
                )
                for source in DATA.glob("*.json"):
                    self.assertEqual(
                        wheel.read(f"avp/utils/data/{source.name}"), source.read_bytes()
                    )
                consumer = Path(out) / "consumer"
                wheel.extractall(consumer)
            subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    f"""
import sys
sys.path.insert(0, {str(consumer)!r})
from avp.artifacts import ArtifactManifest
from avp.utils.endpoints import bundled_endpoints, default_base_url, provider_auth
from avp.utils.pricing import bundled_prices
assert default_base_url(bundled_endpoints(), 'anthropic') == 'https://api.anthropic.com/v1'
assert provider_auth(bundled_endpoints(), 'anthropic').header == 'x-api-key'
assert bundled_prices().models['anthropic/claude-sonnet-4-5'].output > 0
assert ArtifactManifest(avp_version='0.1', run_id='r', artifacts=[]).run_id == 'r'
""",
                ],
                cwd=out,
                check=True,
                capture_output=True,
            )
            self.assert_tar_data(next(Path(out).glob("*.tar.gz")), "src/avp/utils/data")

    def test_typescript_package(self) -> None:
        with tempfile.TemporaryDirectory() as out:
            subprocess.run(
                ["npm", "pack", "--json", "--pack-destination", out],
                cwd=ROOT / "avp-sdk" / "typescript",
                check=True,
                capture_output=True,
            )
            archive = next(Path(out).glob("*.tgz"))
            self.assert_tar_data(archive, "dist/utils/data")
            consumer = Path(out) / "consumer"
            consumer.mkdir()
            # A published package resolves its dependencies from the registry.
            # Use an empty cache so a developer's cached metadata cannot hide
            # failures on a fresh CI runner.
            subprocess.run(
                [
                    "npm",
                    "install",
                    "--cache",
                    str(Path(out) / "npm-cache"),
                    "--ignore-scripts",
                    "--no-audit",
                    "--no-fund",
                    str(archive),
                ],
                cwd=consumer,
                check=True,
            )
            subprocess.run(
                [
                    "node",
                    "--input-type=module",
                    "-e",
                    """
import assert from 'node:assert/strict';
import { bundledPrices } from '@agent-voyager-project/sdk/utils/pricing';
import { bundledEndpoints, defaultBaseUrl, providerAuth } from '@agent-voyager-project/sdk/utils/endpoints';
import { parseCommission } from '@agent-voyager-project/sdk/commission';
import { Recorder } from '@agent-voyager-project/sdk/recorder';
import { parseArtifacts } from '@agent-voyager-project/sdk/artifacts';
assert.equal(parseArtifacts({avp_version:'0.1',run_id:'r',artifacts:[]}).run_id, 'r');
assert.ok(bundledPrices().models['anthropic/claude-sonnet-4-5'].output > 0);
assert.equal(defaultBaseUrl(bundledEndpoints(), 'anthropic'), 'https://api.anthropic.com/v1');
assert.deepEqual(providerAuth(bundledEndpoints(), 'anthropic'), {header:'x-api-key',prefix:''});
const commission = parseCommission({avp_version:'0.1',run_id:'r',prompt:'Hi',model:{provider:'p',id:'m'}});
const snapshots = [];
const rec = new Recorder(async recording => { snapshots.push(recording.trajectory); });
await rec.start({prompt:commission.prompt,model:commission.model});
await rec.response([{type:'text',text:'Hi'}]);
await rec.stop('converged');
assert.equal(snapshots.at(-1).schema_version, 'ATIF-v1.8');
assert.equal(snapshots.at(-1).steps.at(-1).message, 'Hi');
assert.equal(snapshots.at(-1).extra.avp.complete, true);
""",
                ],
                cwd=consumer,
                check=True,
                capture_output=True,
            )


if __name__ == "__main__":
    unittest.main()
