from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "apps" / "web" / "app" / "assessment" / "page.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
PROXY = ROOT / "apps" / "web" / "app" / "api" / "nico" / "[...path]" / "route.ts"
SPANISH_PAGE = ROOT / "apps" / "web" / "app" / "es" / "assessment" / "page.tsx"
SPANISH_LOCALIZER = ROOT / "apps" / "web" / "app" / "es" / "assessment" / "SpanishAssessmentLocalization.tsx"


def test_public_assessment_is_native_two_service_model() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert 'type AssessmentTier = "express" | "comprehensive"' in source
    assert 'type AssessmentTier = "express" | "mid" | "full"' not in source
    assert '(["express", "comprehensive"] as AssessmentTier[])' in source
    assert '(["express", "mid", "full"] as AssessmentTier[])' not in source
    assert '"/assessment/comprehensive-run"' in source
    assert '"/assessment/mid-run"' not in source
    assert '"/assessment/full-run"' not in source


def test_layout_does_not_mutate_tier_buttons_after_render() -> None:
    source = LAYOUT.read_text(encoding="utf-8")

    assert 'import TwoServiceAssessmentGuard from "./TwoServiceAssessmentGuard";' not in source
    assert "<TwoServiceAssessmentGuard />" not in source


def test_frontend_proxy_allows_only_native_public_assessment_routes() -> None:
    source = PROXY.read_text(encoding="utf-8")

    assert "comprehensive-run" in source
    assert "(?:express|mid|full)-run" not in source


def test_spanish_page_uses_shared_locale_props_not_dom_mutation() -> None:
    source = SPANISH_PAGE.read_text(encoding="utf-8")

    assert '<AssessmentPage locale="es-MX" />' in source
    assert "SpanishAssessmentLocalization" not in source
    assert not SPANISH_LOCALIZER.exists()
