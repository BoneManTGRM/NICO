from __future__ import annotations

from pathlib import Path


LOCALIZER = Path("apps/web/app/assessment/AssessmentDynamicSpanishLocalization.tsx")
ROOT_LAYOUT = Path("apps/web/app/layout.tsx")
SPANISH_PAGE = Path("apps/web/app/es/assessment/page.tsx")


def test_spanish_assessment_route_supplies_es_mx_locale() -> None:
    source = SPANISH_PAGE.read_text(encoding="utf-8")
    assert '<AssessmentPage locale="es-MX" />' in source


def test_assessment_localizer_binds_html_language_only_after_existing_spanish_guard() -> None:
    source = LOCALIZER.read_text(encoding="utf-8")

    guard = source.index('if (locale !== "es-MX") return;')
    bind = source.index("const restoreDocumentLanguage = bindDocumentLanguage(locale);")
    assert guard < bind
    assert "root.lang = locale;" in source
    assert 'root.dataset.nicoAssessmentDocumentLanguage = root.lang;' in source
    assert "restoreDocumentLanguage();" in source
    assert "bindDocumentLanguage," in source


def test_root_default_remains_english_for_nonlocalized_routes() -> None:
    source = ROOT_LAYOUT.read_text(encoding="utf-8")
    assert '<html lang="en"' in source


def test_language_binding_does_not_change_assessment_or_delivery_state() -> None:
    source = LOCALIZER.read_text(encoding="utf-8")

    assert "client_delivery_allowed" not in source
    assert "human_review_required" not in source
    assert "/approve" not in source
    assert "report_language" not in source
