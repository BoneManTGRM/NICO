from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "apps" / "web" / "app" / "assessment" / "page.tsx"


def _source() -> str:
    return PAGE.read_text(encoding="utf-8")


def _run_body(source: str) -> str:
    return source.split("async function runAssessment()", 1)[1].split("async function copyMarkdown()", 1)[0]


def _continuation_body(source: str) -> str:
    return source.split("async function continueAssessment(", 1)[1].split("async function runAssessment()", 1)[0]


def test_each_tier_has_one_canonical_start_request() -> None:
    body = _run_body(_source())

    assert body.count("/assessment/github") == 1
    assert body.count("/assessment/mid-run`") == 1
    assert body.count("/assessment/full-run`") == 1
    assert 'assessment_mode: "express"' in body
    assert 'mode: "full"' in body


def test_mid_and_full_continuation_never_restart_the_assessment() -> None:
    body = _continuation_body(_source())

    assert "/assessment/github" not in body
    assert "`${API_URL}/assessment/mid-run`" not in body
    assert "`${API_URL}/assessment/full-run`" not in body
    assert "/assessment/mid-run/${encodeURIComponent(runId)}/status" in body
    assert "/assessment/full-run/${encodeURIComponent(runId)}/status" in body


def test_every_status_poll_uses_the_run_id_returned_by_the_prior_response() -> None:
    body = _continuation_body(_source())

    assert 'const runId = String(current.run_id || "")' in body
    assert 'if (!runId) throw new Error("The assessment response did not include a run ID for autonomous continuation.")' in body
    assert "current = await parseResponse(response)" in body
    assert "runSequence.current" in body
    assert body.count("if (sequence !== runSequence.current) return") >= 2


def test_timeout_preserves_identity_instead_of_starting_a_replacement_run() -> None:
    body = _continuation_body(_source())

    assert "for (let attempt = 1; attempt <= MAX_POLL_ATTEMPTS; attempt += 1)" in body
    assert 'setPhase("timed_out")' in body
    assert "The exact run ID is preserved" in body
    assert "without starting a duplicate run" in body


def test_full_continuation_retains_full_contract_on_every_status_refresh() -> None:
    body = _continuation_body(_source())

    assert 'if (selectedTier === "full")' in body
    assert 'body.mode = "full"' in body
    assert "body.build_reports = true" in body
    assert "body.create_final_review_request = true" in body
    assert "body.tools = FULL_TOOLS" in body
