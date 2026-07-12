from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "apps" / "web" / "app" / "retainer-ops" / "page.tsx"
LAUNCHER = ROOT / "apps" / "web" / "app" / "RetainerAutoEvidenceLauncher.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"


def test_retainer_page_submits_repository_binding_and_business_context_only() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "`${API_URL}/retainer/ops`" in source
    for required in [
        "repository,",
        "baseline_run_id: baselineRunId",
        "timeframe_days: Number(timeframeDays || 30)",
        "roadmap_notes: roadmapNotes",
        "client_update: clientUpdate",
        "retainer_metrics: metrics",
        "budget_priorities: budgetPriorities",
        "refresh_evidence: true",
    ]:
        assert required in source
    request_block = source[source.index("body: JSON.stringify({"):source.index("}),\n      });", source.index("body: JSON.stringify({"))]
    for forbidden in [
        "commit_summary",
        "pr_summary",
        "issue_summary",
        "blockers:",
        "release_notes",
        "deployment_summary",
        "workflow_summary",
    ]:
        assert forbidden not in request_block


def test_retainer_page_has_no_manual_technical_evidence_fields() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "No manual technical summaries" in source
    assert "Roadmap decisions and priorities" in source
    assert "Client update context" in source
    assert "Business or retainer metrics" in source
    assert "Budget and priority context" in source
    for forbidden_label in [
        "Commit summary",
        "PR summary",
        "Issue summary",
        "Release notes",
        ">Blockers<",
    ]:
        assert forbidden_label not in source


def test_retainer_page_discloses_source_identity_and_unverified_scores() -> None:
    source = PAGE.read_text(encoding="utf-8")

    for required in [
        "Observed commit",
        "Baseline run",
        "Snapshot",
        "Scanner",
        "Exact evidence checks",
        "source.checked_at",
        "source.item_count",
        'section.score_calculated ? `${section.score}/100` : "score unavailable"',
        "Client delivery allowed",
        "An empty blocker field is not treated as clear",
    ]:
        assert required in source


def test_command_center_legacy_retainer_form_is_hidden_and_replaced_with_launcher() -> None:
    launcher = LAUNCHER.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'document.querySelector<HTMLElement>("#retainer")' in launcher
    assert 'section.querySelector<HTMLElement>(".command-card")' in launcher
    assert 'button.textContent?.includes("Run Retainer Ops")' in launcher
    assert "legacyForm.hidden = true" in launcher
    assert "legacyButton.hidden = true" in launcher
    assert 'href="/retainer-ops"' in launcher
    assert "Automatic evidence mode" in launcher
    assert "RetainerAutoEvidenceLauncher" in layout
    assert '<a href="/retainer-ops">Retainer Ops</a>' in layout
