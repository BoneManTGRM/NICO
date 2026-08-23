from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_english_and_spanish_routes_use_one_shared_assessment_application() -> None:
    english = source("apps/web/app/assessment/page.tsx")
    spanish = source("apps/web/app/es/assessment/page.tsx")

    assert 'import AssessmentPage from "./AssessmentPage"' in english
    assert '<AssessmentPage locale="en-US" />' in english
    assert 'import AssessmentPage from "../../assessment/AssessmentPage"' in spanish
    assert '<AssessmentPage locale="es-MX" />' in spanish
    assert "useAssessmentRun" not in spanish
    assert "comprehensive-intake" not in spanish


def test_shared_page_uses_canonical_locale_identity_without_parallel_business_logic() -> None:
    page = source("apps/web/app/assessment/AssessmentPage.tsx")
    types = source("apps/web/app/assessment/assessmentTypes.ts")

    assert 'export type CanonicalLocale = "en-US" | "es-MX"' in types
    assert 'export type Locale = LegacyLocale' in types
    assert 'locale = "en-US"' in page
    assert "<AssessmentWorkspace locale={presentationLocale} />" in page
    assert 'locale === "es-MX" ? "es-MX" : "en"' in page


def test_language_switch_preserves_exact_run_and_report_locale_query_state() -> None:
    navigation = source("apps/web/app/PrimaryNavigation.tsx")
    locale = source("apps/web/app/assessment/assessmentLocale.ts")

    assert "localePreservingHref(" in navigation
    assert "currentSearch" in navigation
    assert "currentHash" in navigation
    assert 'data-preserves-assessment-state="true"' in navigation
    assert 'params.set("tier", "comprehensive")' in locale
    assert 'params.delete("lang")' in locale
    assert "params.delete(\"run_id\")" not in locale
    assert "params.delete(\"report_locale\")" not in locale
    assert "new URLSearchParams" in locale


def test_active_navigation_exposes_only_nico_comprehensive() -> None:
    navigation = source("apps/web/app/PrimaryNavigation.tsx")

    assert 'href: "/assessment?tier=comprehensive#assessment"' in navigation
    assert "type AssessmentMode" not in navigation
    assert "normalizeAssessmentMode" not in navigation
    assert "setAssessment" not in navigation
    assert 'data-canonical-product="nico-comprehensive"' in navigation


def test_ui_and_report_locale_preferences_have_separate_authorities() -> None:
    locale = source("apps/web/app/assessment/assessmentLocale.ts")

    assert 'UI_LOCALE_STORAGE_KEY = "nico.ui-locale.v1"' in locale
    assert 'REPORT_LOCALE_STORAGE_KEY = "nico.report-locale.v1"' in locale
    assert 'searchParams.get("report_locale")' in locale
    assert 'searchParams.set("report_locale", locale)' in locale
    assert "persistUiLocale" in locale
    assert "persistReportLocale" in locale
