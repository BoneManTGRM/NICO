#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

REPLACEMENTS = {
    Path("tests/test_postgres_restart_proof.py"): [
        (
            'assert "actions/upload-artifact@v7" in source',
            'assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in source',
        ),
    ],
    Path("tests/test_production_assessment_smoke.py"): [
        (
            'assert "actions/upload-artifact@v7" in source and "retention-days: 90" in source',
            'assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in source and "retention-days: 90" in source',
        ),
    ],
    Path("tests/test_resilience_proof.py"): [
        (
            'assert "actions/upload-artifact@v7" in source',
            'assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in source',
        ),
    ],
    Path("tests/test_scanner_evidence_pipeline_v1.py"): [
        (
            'assert "8ed545766fb4c5054798a02ea17ece0fe7bcab64" in workflow',
            'assert "github.event.pull_request.head.sha" in workflow\n'
            '    assert "inputs.target_sha" in workflow\n'
            '    assert "phase5-verification-package-${{ env.TARGET_SHA }}" in workflow',
        ),
        (
            'assert "retention-days: 30" in workflow',
            'assert "retention-days: 90" in workflow',
        ),
    ],
}


def main() -> int:
    for path, replacements in REPLACEMENTS.items():
        source = path.read_text(encoding="utf-8")
        for old, new in replacements:
            count = source.count(old)
            if count != 1:
                raise SystemExit(f"Expected one occurrence in {path}: {old!r}; observed {count}")
            source = source.replace(old, new)
        path.write_text(source, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
