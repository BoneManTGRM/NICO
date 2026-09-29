"""Keep the resumed main release path compatible with exact-SHA proofs."""
from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class VercelMainDeploymentContractTests(unittest.TestCase):
    def assert_main_deployment_enabled(self, relative_path: str) -> None:
        config = json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
        deployment_enabled = config.get("git", {}).get("deploymentEnabled")
        self.assertIsInstance(deployment_enabled, dict, relative_path)
        self.assertIs(
            deployment_enabled.get("main"),
            True,
            f"{relative_path}: main must deploy before exact-SHA production proofs can run",
        )
        self.assertIsNot(
            config.get("github", {}).get("enabled"),
            False,
            f"{relative_path}: legacy GitHub disable must not block the release path",
        )

    def test_repository_root_allows_main_deployment(self) -> None:
        self.assert_main_deployment_enabled("vercel.json")

    def test_web_project_allows_main_deployment(self) -> None:
        self.assert_main_deployment_enabled("apps/web/vercel.json")


if __name__ == "__main__":
    unittest.main()
