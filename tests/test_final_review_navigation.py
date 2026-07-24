from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAVIGATION = ROOT / "apps" / "web" / "app" / "PrimaryNavigation.tsx"
PAGE = ROOT / "apps" / "web" / "app" / "operations" / "final-review" / "page.tsx"


def test_operator_navigation_exposes_final_review_workspace() -> None:
    source = NAVIGATION.read_text(encoding="utf-8")

    assert '{label: "Final Review", href: "/operations/final-review"}' in source
    assert '{label: "Revisión final", href: "/operations/final-review"}' in source
    assert "final approval" in source
    assert "aprobación final" in source


def test_final_review_page_never_persists_admin_token() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert 'type="password"' in source
    assert '"X-NICO-Admin-Token": adminToken.trim()' in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "document.cookie" not in source
    assert "searchParams.set(\"admin" not in source


def test_final_review_page_supports_both_services_and_all_decisions() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert '<option value="express">Express</option>' in source
    assert '<option value="comprehensive">Comprehensive</option>' in source
    assert 'transition("approved")' in source
    assert 'transition("needs_more_evidence")' in source
    assert 'transition("rejected")' in source
    assert "Download approved final PDF" in source
    assert "Download approved delivery package" in source


def test_final_review_page_uses_a_simple_two_step_workflow() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "<h2>Find the report</h2>" in source
    assert "<h2>Review and decide</h2>" in source
    assert "Load a report to begin final review." in source
    assert "Start final review" in source
    assert "Advanced options" in source
    assert "Exact review data" in source

    advanced_start = source.index("<details className={styles.advanced}>")
    advanced_end = source.index("</details>", advanced_start)
    assert advanced_start < source.index("Customer ID") < advanced_end
    assert advanced_start < source.index("Project ID") < advanced_end


def test_final_review_page_refreshes_truth_after_every_mutation() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "async function refreshAfterMutation" in source
    assert "setResult(await fetchReviewStatus())" in source
    assert source.count("await refreshAfterMutation(payload)") == 2
    assert "Use Reload status before downloading." in source


def test_final_review_page_has_accessible_feedback_and_safe_download_failures() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert 'aria-live="polite"' in source
    assert 'role="alert"' in source
    assert "The approved PDF data is invalid." in source
    assert "Final-review endpoint returned invalid JSON" in source
