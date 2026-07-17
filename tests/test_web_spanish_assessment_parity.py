from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGLISH_PAGE = ROOT / "apps" / "web" / "app" / "assessment" / "page.tsx"
SPANISH_PAGE = ROOT / "apps" / "web" / "app" / "es" / "assessment" / "page.tsx"
SPANISH_HOME = ROOT / "apps" / "web" / "app" / "es" / "page.tsx"
SPANISH_LOCALIZATION = ROOT / "apps" / "web" / "app" / "es" / "assessment" / "SpanishAssessmentLocalization.tsx"


def test_spanish_route_reuses_the_canonical_assessment_component() -> None:
    source = SPANISH_PAGE.read_text(encoding="utf-8")
    assert 'import AssessmentPage from "../../assessment/page"' in source
    assert "<AssessmentPage />" in source
    assert "SpanishAssessmentLocalization" in source


def test_spanish_home_routes_to_the_same_unified_assessment_workflow() -> None:
    source = SPANISH_HOME.read_text(encoding="utf-8")
    assert 'redirect("/es/assessment?tier=express#assessment")' in source


def test_all_tiers_exist_in_canonical_workspace_and_spanish_catalog() -> None:
    english = ENGLISH_PAGE.read_text(encoding="utf-8")
    spanish = SPANISH_LOCALIZATION.read_text(encoding="utf-8")
    for tier in ('"express"', '"mid"', '"full"'):
        assert tier in english
    for label in ("Express", "Intermedia", "Completa"):
        assert f'"{label}"' in spanish


def test_spanish_catalog_covers_primary_assessment_controls() -> None:
    source = SPANISH_LOCALIZATION.read_text(encoding="utf-8")
    required = (
        "EVALUACIÓN EXPRESS",
        "EVALUACIÓN INTERMEDIA",
        "EVALUACIÓN COMPLETA",
        "Ejecutar evaluación",
        "Propietario/nombre del repositorio o URL de GitHub",
        "Se requiere revisión humana",
        "Descargar PDF",
    )
    for text in required:
        assert text in source


def test_spanish_localization_tracks_dynamic_content_and_sets_document_language() -> None:
    source = SPANISH_LOCALIZATION.read_text(encoding="utf-8")
    assert 'document.documentElement.lang = "es"' in source
    assert "new MutationObserver" in source
    assert 'observer.observe(document.body, {childList: true, subtree: true})' in source
