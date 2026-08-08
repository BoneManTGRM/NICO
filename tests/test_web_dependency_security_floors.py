from __future__ import annotations

import json
from pathlib import Path


LOCKFILE = Path("apps/web/package-lock.json")


def _version_tuple(value: str) -> tuple[int, int, int]:
    parts = value.split(".")
    assert len(parts) >= 3, f"unexpected semantic version: {value!r}"
    return tuple(int(part) for part in parts[:3])


def test_nanoid_lockfile_excludes_ghsa_2v37_7h3g_55p8_vulnerable_ranges() -> None:
    payload = json.loads(LOCKFILE.read_text(encoding="utf-8"))
    packages = payload.get("packages") or {}
    nanoid = packages.get("node_modules/nanoid") or {}
    version = str(nanoid.get("version") or "")

    assert version, "package-lock.json must retain the resolved nanoid version"
    major, minor, patch = _version_tuple(version)

    # GHSA-2v37-7h3g-55p8 / CVE-2026-67213 is fixed in 3.3.17 for the
    # transitive 3.x line used by PostCSS and in 5.1.6 for the 5.x line.
    if major == 3:
        assert (major, minor, patch) >= (3, 3, 17)
    elif major == 4:
        raise AssertionError(f"nanoid {version} is within the vulnerable 4.x range")
    elif major == 5:
        assert (major, minor, patch) >= (5, 1, 6)
    else:
        assert major > 5, f"unsupported or vulnerable nanoid version: {version}"
