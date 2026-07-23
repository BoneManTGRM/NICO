from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAVIGATION = ROOT / "apps/web/app/PrimaryNavigation.tsx"
SPANISH_PAGE = ROOT / "apps/web/app/es/assessment/page.tsx"
LANGUAGE_COMPONENT = ROOT / "apps/web/app/es/assessment/SpanishDocumentLanguage.tsx"


def test_spanish_navigation_uses_customer_facing_spanish_terms() -> None:
    source = NAVIGATION.read_text(encoding="utf-8")
    assert 'retainer: "Servicio continuo"' in source
    assert 'label: "Espacios de trabajo del operador"' in source
    assert 'label: "Guía"' in source
    assert 'label: "Escáner a Express"' not in source
    assert 'retainer: "Retainer"' not in source
    assert 'className="global-brand" href="/assessment?tier=express#assessment"' in source


def test_spanish_assessment_sets_document_language_for_runtime_localizers() -> None:
    page = SPANISH_PAGE.read_text(encoding="utf-8")
    component = LANGUAGE_COMPONENT.read_text(encoding="utf-8")
    assert 'import SpanishDocumentLanguage from "./SpanishDocumentLanguage"' in page
    assert "<SpanishDocumentLanguage />" in page
    assert 'document.documentElement.lang = "es-MX"' in component
    assert 'document.body.dataset.nicoLocale = "es-MX"' in component


def test_language_switch_label_remains_english_on_spanish_route_intentionally() -> None:
    source = NAVIGATION.read_text(encoding="utf-8")
    assert 'const languageLabel = spanishActive ? "English" : "Español"' in source
    assert 'aria-label={spanishActive ? "Cambiar a inglés"' in source
