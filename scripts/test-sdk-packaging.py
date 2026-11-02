"""Check that published SDK archives contain the shared price snapshot."""

import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRICES = ROOT / "avp-sdk" / "data" / "avp_prices.json"


class PackagingTests(unittest.TestCase):
    def assert_tar_prices(self, archive: Path, suffix: str) -> None:
        with tarfile.open(archive) as package:
            matches = [entry for entry in package.getmembers() if entry.name.endswith(suffix)]
            self.assertEqual(len(matches), 1)
            self.assertTrue(matches[0].isfile(), "the archive must contain a regular file")
            self.assertEqual(package.extractfile(matches[0]).read(), PRICES.read_bytes())

    def test_python_wheel_and_sdist(self) -> None:
        with tempfile.TemporaryDirectory() as out:
            subprocess.run(
                ["uv", "build", "--offline", "--out-dir", out],
                cwd=ROOT / "avp-sdk" / "python",
                check=True,
                capture_output=True,
            )
            with zipfile.ZipFile(next(Path(out).glob("*.whl"))) as wheel:
                self.assertEqual(wheel.read("avp/utils/data/avp_prices.json"), PRICES.read_bytes())
            self.assert_tar_prices(
                next(Path(out).glob("*.tar.gz")), "/src/avp/utils/data/avp_prices.json"
            )

    def test_rust_crate(self) -> None:
        with tempfile.TemporaryDirectory() as out:
            subprocess.run(
                [
                    "cargo",
                    "package",
                    "--offline",
                    "--allow-dirty",
                    "--no-verify",
                    "--target-dir",
                    out,
                ],
                cwd=ROOT / "avp-sdk" / "rust",
                check=True,
                capture_output=True,
            )
            self.assert_tar_prices(
                next((Path(out) / "package").glob("*.crate")),
                "/src/utils/data/avp_prices.json",
            )


if __name__ == "__main__":
    unittest.main()
