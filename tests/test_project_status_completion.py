from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "PROJECT_STATUS.md"
MANIFEST = ROOT / "tests" / "fixtures" / "golden" / "manifest.json"
DEMONSTRATION_WORKFLOW = ROOT / ".github" / "workflows" / "recorded-golden-demonstration.yml"
DEMONSTRATION_BUILDER = ROOT / "scripts" / "build_golden_demonstration.py"
POSTGRES_RESTART_WORKFLOW = ROOT / ".github" / "workflows" / "postgres-restart-proof.yml"
POSTGRES_RESTART_BUILDER = ROOT / "scripts" / "postgres_restart_proof.py"
RESILIENCE_WORKFLOW = ROOT / ".github" / "workflows" / "resilience-proof.yml"
RESILIENCE_BUILDER = ROOT / "scripts" / "build_resilience_proof.py"


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

    assert completed == 10
    assert total == 12
    assert checked == completed
    assert checked + unchecked == total


def test_completed_evidence_workstreams_are_checked_and_live_proof_remains_unchecked() -> None:
    source = _source()

    assert "- [x] Restart, durable-storage, recovery, observability, and graceful-degradation proof." in source
    assert "- [x] Additional representative golden fixtures and recorded evidence-bound demonstrations with no fabricated live claims." in source
    assert "- [ ] Deployed browser/API E2E proof for unified Express, Mid, and Full with exact-run identity and no duplicate starts." in source
    assert "This completion does not count as deployed browser/API E2E proof or live production evidence." in source
    assert "This completion does not claim that Railway restarted" in source


def test_golden_completion_evidence_references_existing_contracts() -> None:
    source = _source()

    assert MANIFEST.is_file()
    assert DEMONSTRATION_WORKFLOW.is_file()
    assert DEMONSTRATION_BUILDER.is_file()
    assert "`tests/fixtures/golden/manifest.json`" in source
    assert "`.github/workflows/recorded-golden-demonstration.yml`" in source
    assert "`scripts/build_golden_demonstration.py`" in source


def test_resilience_completion_evidence_references_existing_contracts() -> None:
    source = _source()

    assert POSTGRES_RESTART_WORKFLOW.is_file()
    assert POSTGRES_RESTART_BUILDER.is_file()
    assert RESILIENCE_WORKFLOW.is_file()
    assert RESILIENCE_BUILDER.is_file()
    assert "`.github/workflows/postgres-restart-proof.yml`" in source
    assert "`.github/workflows/resilience-proof.yml`" in source
    assert "`scripts/postgres_restart_proof.py`" in source
    assert "`scripts/build_resilience_proof.py`" in source
    assert "Scanner recovery remains operator-controlled" in source


def test_remaining_execution_order_contains_only_unfinished_workstreams() -> None:
    source = _source()
    remaining = source.split("## Remaining execution order", 1)[1].split("## Resilience completion evidence", 1)[0]

    assert "Deployed Express, Mid, and Full browser/API E2E proof" in remaining
    assert "CLI and service modularization" in remaining
    assert "Restart, persistence, observability, recovery, and graceful-degradation proof" not in remaining
    assert "Additional golden fixtures" not in remaining
    assert "**4–7 small, reviewable pull requests**" in remaining
