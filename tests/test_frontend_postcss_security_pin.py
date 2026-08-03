from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"


def test_postcss_override_and_lock_use_patched_version() -> None:
    package = json.loads((WEB / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((WEB / "package-lock.json").read_text(encoding="utf-8"))

    assert package["overrides"]["postcss"] == "8.5.23"
    postcss = lock["packages"]["node_modules/postcss"]
    assert postcss["version"] == "8.5.23"
    assert postcss["resolved"].endswith("/postcss-8.5.23.tgz")
    assert postcss["integrity"].startswith("sha512-")
