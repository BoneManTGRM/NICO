from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY_GUARD = ROOT / "apps" / "web" / "app" / "TwoServiceAssessmentGuard.tsx"
ASSESSMENT = ROOT / "apps" / "web" / "app" / "assessment"
WORKSPACE = ASSESSMENT / "AssessmentWorkspace.tsx"
HOOK = ASSESSMENT / "useAssessmentRun.ts"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
REDIRECT = ROOT / "apps" / "web" / "app" / "LegacyFullRunRedirect.tsx"


def test_public_workspace_has_one_canonical_comprehensive_assessment() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")
    rendered = source.split("return <main", 1)[1]

    assert 'data-workspace="assessment"' in rendered
    assert 'data-engagement-type="comprehensive"' in rendered
    assert 'data-assessment-service-count' not in rendered
    assert 'data-canonical-assessment="strategic"' in rendered
    assert 'data-customer-facing-assessment="comprehensive"' in rendered
    assert '(["express", "comprehensive"] as Service[])' not in rendered
    assert 'aria-label="Assessment type"' not in rendered


def test_legacy_query_names_normalize_to_comprehensive_in_controller() -> None:
    source = HOOK.read_text(encoding="utf-8")

    assert 'url.searchParams.get("tier") !== "comprehensive"' in source
    assert 'url.searchParams.set("tier", "comprehensive")' in source
    assert 'const service: Service = "comprehensive"' in source


def test_layout_does_not_install_the_retired_two_service_guard() -> None:
    source = LAYOUT.read_text(encoding="utf-8")

    assert not LEGACY_GUARD.exists()
    assert "TwoServiceAssessmentGuard" not in source
    assert "MutationObserver" not in source


def test_old_full_route_enters_comprehensive() -> None:
    source = REDIRECT.read_text(encoding="utf-8")
    assert 'window.location.replace("/assessment?tier=comprehensive#assessment")' in source
