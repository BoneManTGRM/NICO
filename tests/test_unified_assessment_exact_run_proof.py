from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "apps" / "web" / "app" / "assessment" / "useAssessmentRun.ts"


def source() -> str:
    return HOOK.read_text(encoding="utf-8")


def run_body() -> str:
    return source().split("async function run()", 1)[1]


def continuation_body() -> str:
    return source().split("async function continueRun(", 1)[1].split("async function run()", 1)[0]


def test_public_assessment_has_one_canonical_start_request() -> None:
    body = run_body()
    assert body.count('"/assessment/comprehensive-intake"') == 1
    assert "requestWithRetry(" in body
    assert '"/assessment/express-run"' not in body
    assert '"/assessment/mid-run"' not in body
    assert '"/assessment/full-run"' not in body
    assert 'assessment_depth: "strategic"' in body


def test_comprehensive_continues_the_exact_run_without_restarting() -> None:
    body = continuation_body()
    assert '"/assessment/comprehensive-intake"' not in body
    assert "/assessment/comprehensive-run/${encodeURIComponent(runId)}/continue" in body
    assert "recoverRun(runId, {" in body
    assert "current = preserveRunIdentity(continued" in body


def test_every_continuation_uses_the_run_id_returned_by_the_prior_response() -> None:
    body = continuation_body()
    assert 'const runId = String(current.run_id || "")' in body
    assert 'if (!runId) throw new AssessmentApiError(copy.runIdMissing, {' in body
    assert 'code: "assessment_run_id_missing"' in body
    assert "const continued = await requestWithRetry(" in body
    assert "current = preserveRunIdentity(continued" in body
    assert "sequence.current" in body
    assert body.count("if (token !== sequence.current) return") >= 1


def test_timeout_preserves_identity_instead_of_starting_a_replacement_run() -> None:
    body = continuation_body()
    assert "for (let count = 1; count <= MAX_POLL_ATTEMPTS; count += 1)" in body
    assert 'setPhase("timed_out")' in body
    assert 'setResult(current)' in body
    assert '"/assessment/comprehensive-intake"' not in body


def test_comprehensive_continuation_advances_one_stage_on_the_same_run() -> None:
    body = continuation_body()
    assert "/assessment/comprehensive-run/${encodeURIComponent(runId)}/continue" in body
    assert 'body: JSON.stringify({max_stages: 1})' in body
    assert 'method: "POST"' in body
