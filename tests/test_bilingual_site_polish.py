from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_root_layout_installs_shared_polish_without_hardcoded_english_banner() -> None:
    layout = _read("apps/web/app/layout.tsx")

    assert 'import "../styles/site-polish-v2.css";' in layout
    assert "<WorkflowCallout />" in layout
    assert "Assessment workflow:</b> Start Express" not in layout
    assert 'className="nico-app"' in layout


def test_workflow_banner_has_structural_english_and_mexican_spanish_parity() -> None:
    source = _read("apps/web/app/WorkflowCallout.tsx")

    assert "From repository evidence to an approval-ready report" in source
    assert "De la evidencia del repositorio a un informe listo para aprobación" in source
    assert 'title: "Run"' in source
    assert 'title: "Iniciar"' in source
    assert 'title: "Verify"' in source
    assert 'title: "Verificar"' in source
    assert 'title: "Approve"' in source
    assert 'title: "Aprobar"' in source
    assert 'lang={spanish ? "es-MX" : undefined}' in source
    assert 'pathname.startsWith("/assessment")' in source
    assert 'pathname.startsWith("/es/assessment")' in source
    assert source.count("number: \"01\"") == 2
    assert source.count("number: \"02\"") == 2
    assert source.count("number: \"03\"") == 2


def test_navigation_exposes_equal_bilingual_brand_and_state_preserving_language_controls() -> None:
    source = _read("apps/web/app/PrimaryNavigation.tsx")
    locale = _read("apps/web/app/assessment/assessmentLocale.ts")

    assert "Evidence-bound technical assessment" in source
    assert "Evaluación técnica vinculada a evidencia" in source
    assert "Ejecutar evaluación" in source
    assert "Revisión final" in source
    assert "language-switcher" in source
    assert "localePreservingHref(" in source
    assert 'data-preserves-assessment-state="true"' in source
    assert 'const assessmentPath = locale === "es-MX" ? "/es/assessment" : "/assessment"' in source
    assert 'targetPath = `${spanish ? "/es/assessment" : "/assessment"}${suffix}`' in locale
    assert 'params.set("tier", "comprehensive")' in locale
    assert 'params.delete("run_id")' not in locale
    assert 'params.delete("report_locale")' not in locale


def test_shared_polish_covers_navigation_workflow_content_and_accessibility() -> None:
    styles = _read("apps/web/styles/site-polish-v2.css")

    for selector in (
        ".global-brand-mark",
        ".language-switcher",
        ".workflow-banner",
        ".workflow-banner-steps",
        ".workflow-boundary",
        "body[data-nico-locale=\"es-MX\"]",
        "@media (prefers-reduced-motion: reduce)",
    ):
        assert selector in styles

    assert "outline: 2px solid #67e8f9" in styles
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in styles


def test_spanish_route_sets_document_and_body_locale_metadata() -> None:
    source = _read("apps/web/app/es/assessment/SpanishDocumentLanguage.tsx")

    assert 'document.documentElement.lang = "es-MX"' in source
    assert 'document.documentElement.dataset.nicoLocale = "es-MX"' in source
    assert 'document.body.dataset.nicoLocale = "es-MX"' in source
    assert 'document.documentElement.dir = "ltr"' in source
