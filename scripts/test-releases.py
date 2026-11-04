"""Release tags must identify the exact package version being built."""

import unittest
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

    def test_dirty_tree_cannot_be_tagged(self) -> None:
        with patch.object(release, "run", return_value=" M file") as run:
            with self.assertRaisesRegex(ValueError, "working-tree"):
                release.tag("cli")
            run.assert_called_once_with("git", "status", "--porcelain")


if __name__ == "__main__":
    unittest.main()
