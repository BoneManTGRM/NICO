from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "apps" / "web" / "app" / "assessment"
ENGLISH_PAGE = ASSESSMENT / "page.tsx"
WORKSPACE = ASSESSMENT / "AssessmentWorkspace.tsx"
COPY = ASSESSMENT / "assessmentCopy.ts"
HOOK = ASSESSMENT / "useAssessmentRun.ts"
SPANISH_PAGE = ROOT / "apps" / "web" / "app" / "es" / "assessment" / "page.tsx"
SPANISH_HOME = ROOT / "apps" / "web" / "app" / "es" / "page.tsx"
LEGACY_LOCALIZATION = ROOT / "apps" / "web" / "app" / "es" / "assessment" / "SpanishAssessmentLocalization.tsx"


def shared_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in (WORKSPACE, COPY, HOOK))


def test_spanish_route_reuses_the_canonical_assessment_component_with_locale_prop() -> None:
    source = SPANISH_PAGE.read_text(encoding="utf-8")
    assert 'import AssessmentPage from "../../assessment/page"' in source
    assert '<AssessmentPage locale="es-MX" />' in source
    assert "SpanishAssessmentLocalization" not in source


def test_english_page_is_a_thin_wrapper_around_the_same_workspace() -> None:
    source = ENGLISH_PAGE.read_text(encoding="utf-8")
    assert 'import AssessmentWorkspace from "./AssessmentWorkspace"' in source
    assert '<AssessmentWorkspace locale={locale} />' in source


def test_spanish_home_routes_to_the_same_unified_assessment_workflow() -> None:
    source = SPANISH_HOME.read_text(encoding="utf-8")
    assert 'redirect("/es/assessment?tier=express#assessment")' in source


def test_shared_catalog_contains_one_comprehensive_assessment() -> None:
    source = shared_source()
    rendered = WORKSPACE.read_text(encoding="utf-8").split("return <main", 1)[1]

    assert 'const service: Service = "comprehensive"' in source
    assert 'data-assessment-service-count="1"' in rendered
    assert 'data-customer-facing-assessment="comprehensive"' in rendered
    assert 'EVALUACIÓN INTEGRAL NICO' in source
    assert 'EVALUACIÓN INTERMEDIA' not in source
    assert 'EVALUACIÓN COMPLETA' not in source


def test_spanish_catalog_covers_primary_assessment_controls() -> None:
    source = shared_source()
    required = (
        "EVALUACIÓN INTEGRAL NICO",
        "Ejecutar evaluación NICO",
        "Propietario/nombre del repositorio o URL de GitHub",
        "Se requiere revisión humana",
        "Descargar PDF final",
        "El informe final está completo",
        "no es necesario rehacer el informe",
    )
    for text in required:
        assert text in source
    assert "Descargar PDF preliminar" not in source


def test_locale_is_static_and_does_not_mutate_the_rendered_dom() -> None:
    source = shared_source()
    assert 'document.documentElement.lang = locale' in source
    assert "new MutationObserver" not in source
    assert "observer.observe" not in source
    assert not LEGACY_LOCALIZATION.exists()
