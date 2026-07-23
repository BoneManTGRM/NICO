from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_JSON = ROOT / "apps" / "web" / "package.json"
PACKAGE_LOCK = ROOT / "apps" / "web" / "package-lock.json"


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def test_postcss_override_and_lock_remain_above_the_known_vulnerable_range() -> None:
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    lock = json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))

    override = package["overrides"]["postcss"]
    locked = lock["packages"]["node_modules/postcss"]

    assert locked["version"] == override
    assert _version_tuple(override) >= (8, 5, 12)
    assert locked["resolved"].endswith(f"/postcss-{override}.tgz")
    assert locked["integrity"].startswith("sha512-")
