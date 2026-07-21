from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY_GUARD = ROOT / "apps" / "web" / "app" / "TwoServiceAssessmentGuard.tsx"
WORKSPACE = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentWorkspace.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
REDIRECT = ROOT / "apps" / "web" / "app" / "LegacyFullRunRedirect.tsx"


def test_public_workspace_has_native_express_and_comprehensive_only() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")
    rendered = source.split("return <main", 1)[1]

    assert 'type Service = "express" | "comprehensive"' in source
    assert 'data-assessment-service-count="2"' in rendered
    assert '(["express", "comprehensive"] as Service[])' in rendered
    assert 'copy.services[value].label' in rendered


def test_old_query_names_normalize_to_comprehensive_inside_react_state() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")

    assert '["comprehensive", "mid", "full", "deep"]' in source
    assert '? "comprehensive" : "express"' in source
    assert 'url.searchParams.set("tier", next)' in source


def test_layout_does_not_install_a_dom_rewriting_two_service_guard() -> None:
    source = LAYOUT.read_text(encoding="utf-8")

    assert not LEGACY_GUARD.exists()
    assert "TwoServiceAssessmentGuard" not in source
    assert "MutationObserver" not in source


def test_old_full_route_enters_comprehensive() -> None:
    source = REDIRECT.read_text(encoding="utf-8")
    assert 'window.location.replace("/assessment?tier=comprehensive#assessment")' in source
