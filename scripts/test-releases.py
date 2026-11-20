"""Release tags must identify the exact package version being built."""

import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

import release


class ReleaseTests(unittest.TestCase):
    def test_tag_round_trips_each_package(self) -> None:
        for package in release.PACKAGES:
            with self.subTest(package=package):
                self.assertEqual(release.package_for_tag(release.release_tag(package)), package)

    def test_wrong_versions_and_unrelated_tags_cannot_publish(self) -> None:
        for tag in [
            "sdk-python-v999.0",
            "agent-pi-v0.1.1",
            "pypi-v0.5.0",
            "cli-v",
            "sdk-typescript-v0.1.0",
        ]:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                release.package_for_tag(tag)

    def test_dependents_install_a_released_sdk(self) -> None:
        self.assertIsNone(release.sdk_url("sdk-python"))
        self.assertIsNone(release.sdk_url("sdk-typescript"))
        for package in release.PACKAGES:
            if package.startswith("sdk-"):
                continue
            with self.subTest(package=package):
                url = release.sdk_url(package)
                self.assertIn("/releases/download/sdk-", url)
                self.assertTrue(url.endswith((".whl", ".tgz")))

    def test_dirty_tree_cannot_be_tagged(self) -> None:
        with patch.object(release, "run", return_value=" M file") as run:
            with self.assertRaisesRegex(ValueError, "working-tree"):
                release.tag("cli")
            run.assert_called_once_with("git", "status", "--porcelain")

    def test_unpublished_sdk_prevents_adapter_release(self) -> None:
        requests = []

        class MissingRelease(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                requests.append(self.path)
                self.send_error(404, "SDK has not been released")

            do_HEAD = do_GET

            def log_message(self, *args) -> None:
                pass

        with HTTPServer(("127.0.0.1", 0), MissingRelease) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            artifact = "/agent_voyager_project-999.0.0-py3-none-any.whl"
            url = f"http://127.0.0.1:{server.server_port}{artifact}"
            try:
                with (
                    tempfile.TemporaryDirectory() as directory,
                    patch.object(release, "sdk_url", return_value=url),
                ):
                    out = Path(directory)
                    with self.assertRaises(subprocess.CalledProcessError):
                        release.build("agent-pydantic-ai", out)
                    self.assertTrue(list(out.glob("*.whl")))
                    self.assertIn(artifact, requests)
                    self.assertFalse((out / "release.json").exists())
                    self.assertFalse((out / "SHA256SUMS").exists())
            finally:
                server.shutdown()
                thread.join()


if __name__ == "__main__":
    unittest.main()
