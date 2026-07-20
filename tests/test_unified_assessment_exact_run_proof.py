from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentWorkspace.tsx"


def _source() -> str:
    return WORKSPACE.read_text(encoding="utf-8")


def _run_body(source: str) -> str:
    return source.split("async function run()", 1)[1].split("async function copyMarkdown()", 1)[0]


def _continuation_body(source: str) -> str:
    return source.split("async function continueRun(", 1)[1].split("async function run()", 1)[0]


def test_each_public_service_has_one_canonical_start_request() -> None:
    body = _run_body(_source())

    assert body.count('"/assessment/express-run"') == 1
    assert body.count('"/assessment/comprehensive-intake"') == 1
    assert 'assessment_mode: "express"' in body
    assert '"/assessment/mid-run"' not in body
    assert '"/assessment/full-run"' not in body


def test_both_services_continue_the_exact_run_without_restarting() -> None:
    body = _continuation_body(_source())

    assert '"/assessment/express-run"' not in body
    assert '"/assessment/comprehensive-intake"' not in body
    assert "/assessment/express-run/${encodeURIComponent(runId)}/status" in body
    assert "/assessment/comprehensive-run/${encodeURIComponent(runId)}/continue" in body


def test_every_continuation_uses_the_run_id_returned_by_the_prior_response() -> None:
    body = _continuation_body(_source())

    assert 'const runId = String(current.run_id || "")' in body
    assert 'if (!runId) throw new Error(copy.runIdMissing)' in body
    assert "current = await json(await fetch" in body
    assert "sequence.current" in body
    assert body.count("if (token !== sequence.current) return") >= 1


def test_timeout_preserves_identity_instead_of_starting_a_replacement_run() -> None:
    body = _continuation_body(_source())

    assert "for (let count = 1; count <= MAX_POLL_ATTEMPTS; count += 1)" in body
    assert 'setPhase("timed_out")' in body
    assert 'setResult(current)' in body
    assert '"/assessment/express-run"' not in body
    assert '"/assessment/comprehensive-intake"' not in body


def test_comprehensive_continuation_advances_one_stage_on_the_same_run() -> None:
    body = _continuation_body(_source())

    assert 'if (selected === "comprehensive")' in body
    assert "/assessment/comprehensive-run/${encodeURIComponent(runId)}/continue" in body
    assert 'body: JSON.stringify({max_stages: 1})' in body
    assert 'method: "POST"' in body
