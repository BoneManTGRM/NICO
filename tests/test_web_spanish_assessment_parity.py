from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGLISH_PAGE = ROOT / "apps" / "web" / "app" / "assessment" / "page.tsx"
WORKSPACE = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentWorkspace.tsx"
SPANISH_PAGE = ROOT / "apps" / "web" / "app" / "es" / "assessment" / "page.tsx"
SPANISH_HOME = ROOT / "apps" / "web" / "app" / "es" / "page.tsx"
LEGACY_LOCALIZATION = ROOT / "apps" / "web" / "app" / "es" / "assessment" / "SpanishAssessmentLocalization.tsx"


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


def test_shared_catalog_contains_exactly_express_and_comprehensive_services() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")
    rendered = source.split("return <main", 1)[1]

    assert 'type Service = "express" | "comprehensive"' in source
    assert '(["express", "comprehensive"] as Service[])' in rendered
    assert 'label: "Express"' in source
    assert 'label: "Comprehensive"' in source
    assert 'label: "Integral"' in source
    assert 'EVALUACIÓN INTEGRAL' in source
    assert 'EVALUACIÓN INTERMEDIA' not in source
    assert 'EVALUACIÓN COMPLETA' not in source


def test_spanish_catalog_covers_primary_assessment_controls() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")
    required = (
        "EVALUACIÓN EXPRESS",
        "EVALUACIÓN INTEGRAL",
        "Ejecutar",
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
    source = WORKSPACE.read_text(encoding="utf-8")

    assert 'document.documentElement.lang = locale' in source
    assert "new MutationObserver" not in source
    assert "observer.observe" not in source
    assert not LEGACY_LOCALIZATION.exists()
