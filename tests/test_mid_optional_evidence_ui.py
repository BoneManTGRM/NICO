from __future__ import annotations

from pathlib import Path


COMPANION = Path(__file__).resolve().parents[1] / "apps" / "web" / "app" / "MidAssessmentCompanion.tsx"
LAYOUT = Path(__file__).resolve().parents[1] / "apps" / "web" / "app" / "layout.tsx"


def _companion() -> str:
    return COMPANION.read_text(encoding="utf-8")


def test_companion_is_mounted_through_root_layout():
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'import MidAssessmentCompanion from "./MidAssessmentCompanion"' in layout
    assert "<MidAssessmentCompanion />" in layout
    assert "unified Express/Mid intake" in layout


def test_companion_renders_only_on_command_center_after_mid_run_exists():
    source = _companion()

    assert 'window.location.pathname === "/"' in source
    assert "if (!active || !runId) return null" in source
    assert 'id="mid-evidence-console"' in source
    assert 'runId.startsWith("midrun_")' not in source
    assert 'resolvedRunId.startsWith("midrun_")' in source


def test_successful_mid_responses_are_observed_without_intercepting_unrelated_requests():
    source = _companion()

    assert 'path === "/assessment/mid-run"' in source
    assert "isMidStatusPath(path)" in source
    assert "isMidEvidencePath(path)" in source
    assert "if (!targeted || !response.ok) return response" in source
    assert "response.clone().json()" in source
    assert "window.fetch = wrappedFetch" in source
    assert "if (window.fetch === wrappedFetch) window.fetch = originalFetch" in source


def test_one_time_capability_is_removed_from_safe_result_and_kept_in_session_only():
    source = _companion()

    assert "delete safe.optional_evidence_submission" in source
    assert 'const TOKEN_PREFIX = "nico.mid.evidence_token."' in source
    assert "sessionStorage.setItem(TOKEN_PREFIX + resolvedRunId, token)" in source
    assert "sessionStorage.getItem(TOKEN_PREFIX + runId)" in source
    assert "sessionStorage.removeItem(TOKEN_PREFIX + runId)" in source
    assert "optional_evidence_submission" not in source.split("return <div", 1)[1]
    assert "The one-time submission capability is not available" in source


def test_optional_evidence_form_contains_all_supported_fields_and_guardrails():
    source = _companion()
    fields = [
        "application_url",
        "ios_build_access",
        "android_build_access",
        "architecture_documents",
        "product_requirements",
        "stakeholder_questionnaire",
        "meeting_transcripts",
        "existing_roadmap",
        "business_priorities",
    ]
    for field in fields:
        assert f'"{field}"' in source

    assert "Additional evidence, optional" in source
    assert "Attach optional evidence" in source
    assert "It is not repository proof" in source
    assert "cannot change a score automatically" in source
    assert "requires human validation" in source
    assert "referrerPolicy: \"no-referrer\"" in source


def test_truth_status_ui_collapses_verified_sections_and_expands_exceptions():
    source = _companion()

    assert 'item.truth_status === "Verified"' in source
    assert 'item.truth_status !== "Verified"' in source
    assert "Sections not automatically verified" in source
    assert "Verified automatically — evidence available" in source
    assert '<details className="result-card" open' in source
    assert "Unsupported claims permitted" in source


def test_calculated_coverage_is_displayed_with_method_and_units():
    source = _companion()

    assert "coverage?.calculated" in source
    assert "coverage.percent" in source
    assert "Coverage is based on explicit evidence units, not the maturity score" in source
    assert "Coverage units" in source
    assert "coverage.method" in source
    assert "coverage.numerator" in source
    assert "coverage.denominator" in source


def test_optional_evidence_submission_updates_safe_state_without_rendering_token():
    source = _companion()

    assert "/assessment/mid-run/${encodeURIComponent(runId)}/evidence" in source
    assert "JSON.stringify({token, ...fields})" in source
    assert "data.status !== \"submitted\"" in source
    assert "optional_evidence: data.optional_evidence" in source
    rendered = source.split("return <div", 1)[1]
    assert "{token}" not in rendered
    assert "submission?.token" not in rendered
