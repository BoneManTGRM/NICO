from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "apps" / "web" / "app" / "TwoServiceAssessmentGuard.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
REDIRECT = ROOT / "apps" / "web" / "app" / "LegacyFullRunRedirect.tsx"


def test_public_workspace_has_express_and_comprehensive_only() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert 'express.textContent = "Express"' in source
    assert 'comprehensive.textContent = "Comprehensive"' in source
    assert 'selector.dataset.nicoCustomerAssessmentCount = "2"' in source
    assert 'button.hidden = true' in source
    assert 'button.tabIndex = -1' in source


def test_old_query_names_normalize_to_comprehensive() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert 'new Set(["mid", "full", "deep"])' in source
    assert 'url.searchParams.set("tier", "comprehensive")' in source
    assert 'comprehensive.dataset.nicoPublicService = "comprehensive"' in source


def test_layout_installs_two_service_guard() -> None:
    source = LAYOUT.read_text(encoding="utf-8")
    rendered = source.split("export default function RootLayout", 1)[1]
    assert 'import TwoServiceAssessmentGuard from "./TwoServiceAssessmentGuard";' in source
    assert "<TwoServiceAssessmentGuard />" in rendered
    assert rendered.index("<TwoServiceAssessmentGuard />") < rendered.index("{children}")


def test_old_full_route_enters_comprehensive() -> None:
    source = REDIRECT.read_text(encoding="utf-8")
    assert 'window.location.replace("/assessment?tier=comprehensive#assessment")' in source
