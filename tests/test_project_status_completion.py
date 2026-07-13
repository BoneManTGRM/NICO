from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "PROJECT_STATUS.md"
MANIFEST = ROOT / "tests" / "fixtures" / "golden" / "manifest.json"
DEMONSTRATION_WORKFLOW = ROOT / ".github" / "workflows" / "recorded-golden-demonstration.yml"
DEMONSTRATION_BUILDER = ROOT / "scripts" / "build_golden_demonstration.py"


def _source() -> str:
    return STATUS.read_text(encoding="utf-8")


def test_declared_completion_count_matches_checked_roadmap_items() -> None:
    source = _source()
    match = re.search(r"Completed major workstreams: \*\*(\d+) of (\d+)\*\*\.", source)

    assert match
    completed = int(match.group(1))
    total = int(match.group(2))
    checked = len(re.findall(r"^- \[x\] ", source, flags=re.MULTILINE))
    unchecked = len(re.findall(r"^- \[ \] ", source, flags=re.MULTILINE))

    assert completed == 9
    assert total == 12
    assert checked == completed
    assert checked + unchecked == total


def test_golden_workstream_is_checked_and_live_proof_remains_unchecked() -> None:
    source = _source()

    assert "- [x] Additional representative golden fixtures and recorded evidence-bound demonstrations with no fabricated live claims." in source
    assert "- [ ] Deployed browser/API E2E proof for unified Express, Mid, and Full with exact-run identity and no duplicate starts." in source
    assert "This completion does not count as deployed browser/API E2E proof or live production evidence." in source


def test_golden_completion_evidence_references_existing_contracts() -> None:
    source = _source()

    assert MANIFEST.is_file()
    assert DEMONSTRATION_WORKFLOW.is_file()
    assert DEMONSTRATION_BUILDER.is_file()
    assert "`tests/fixtures/golden/manifest.json`" in source
    assert "`.github/workflows/recorded-golden-demonstration.yml`" in source
    assert "`scripts/build_golden_demonstration.py`" in source


def test_remaining_execution_order_contains_only_unfinished_workstreams() -> None:
    source = _source()
    remaining = source.split("## Remaining execution order", 1)[1].split("## Golden-fixture completion evidence", 1)[0]

    assert "Deployed Express, Mid, and Full browser/API E2E proof" in remaining
    assert "Restart, persistence, observability, recovery, and graceful-degradation proof" in remaining
    assert "CLI and service modularization" in remaining
    assert "Additional golden fixtures" not in remaining
    assert "**5–8 small, reviewable pull requests**" in remaining
