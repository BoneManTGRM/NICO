from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "apps" / "web" / "app" / "assessment"
ENGLISH_ROUTE = ASSESSMENT / "page.tsx"
CANONICAL_PAGE = ASSESSMENT / "AssessmentPage.tsx"
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
    assert 'import AssessmentPage from "../../assessment/AssessmentPage"' in source
    assert '<AssessmentPage locale="es-MX" />' in source
    assert "SpanishAssessmentLocalization" not in source
    assert "useAssessmentRun" not in source


def test_english_route_is_a_thin_wrapper_around_the_single_canonical_page() -> None:
    route = ENGLISH_ROUTE.read_text(encoding="utf-8")
    page = CANONICAL_PAGE.read_text(encoding="utf-8")
    assert 'import AssessmentPage from "./AssessmentPage"' in route
    assert '<AssessmentPage locale="en-US" />' in route
    assert 'import AssessmentWorkspace from "./AssessmentWorkspace"' in page
    assert '<AssessmentWorkspace locale={presentationLocale} />' in page
    assert 'locale === "es-MX" ? "es-MX" : "en"' in page
    assert "<AssessmentHydrationContract" in page


def test_spanish_home_routes_to_the_same_unified_assessment_workflow() -> None:
    source = SPANISH_HOME.read_text(encoding="utf-8")
    assert 'redirect("/es/assessment?tier=comprehensive#assessment")' in source
    assert "tier=express" not in source


def test_shared_catalog_contains_one_comprehensive_assessment() -> None:
    source = shared_source()
    rendered = WORKSPACE.read_text(encoding="utf-8").split("return <main", 1)[1]

    assert 'const service: Service = "comprehensive"' in source
    assert 'data-workspace="assessment"' in rendered
    assert 'data-engagement-type="comprehensive"' in rendered
    assert 'data-assessment-service-count' not in rendered
    assert 'data-customer-facing-assessment="comprehensive"' in rendered
    assert 'EVALUACIÓN TÉCNICA Y ASESORÍA DE INGENIERÍA' in source
    assert 'EVALUACIÓN INTERMEDIA' not in source
    assert 'EVALUACIÓN COMPLETA' not in source


def test_spanish_catalog_covers_primary_assessment_controls() -> None:
    source = shared_source()
    required = (
        "EVALUACIÓN TÉCNICA Y ASESORÍA DE INGENIERÍA",
        "Crear encargo y capturar instantánea del repositorio",
        "Propietario/nombre del repositorio o URL de GitHub",
        "Revisión interna requerida",
        "Descargar PDF para revisión",
        "El análisis automatizado terminó.",
        "Un revisor autorizado de NICO debe aprobar esta edición exacta",
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
