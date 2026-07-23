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
    assert '"X-NICO-Admin-Token": adminToken' in source
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
