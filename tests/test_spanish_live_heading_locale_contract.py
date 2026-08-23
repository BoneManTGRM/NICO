from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_spanish_live_localization_uses_authoritative_canonical_page_locale() -> None:
    page = (ROOT / "apps/web/app/assessment/AssessmentPage.tsx").read_text()
    localization = (
        ROOT / "apps/web/app/assessment/AssessmentDynamicSpanishLocalization.tsx"
    ).read_text()

    assert 'locale === "es-MX" ? "es-MX" : "en"' in page
    assert '<AssessmentDynamicSpanishLocalization locale={presentationLocale} />' in page
    assert '({locale}: {locale: "en" | "es-MX"})' in localization
    assert 'if (locale !== "es-MX") return;' in localization
    assert 'document.documentElement.lang.toLowerCase().startsWith("es")' not in localization
    assert '["comprehensive run", "Evaluación integral"]' in localization
    assert 'script, style, code, pre, textarea, [data-no-localize=\'true\']' in localization


def test_english_live_heading_is_not_rewritten_by_spanish_localizer() -> None:
    localization = (
        ROOT / "apps/web/app/assessment/AssessmentDynamicSpanishLocalization.tsx"
    ).read_text()

    assert 'if (locale !== "es-MX") return;' in localization
    assert '["comprehensive run", "Evaluación integral"]' in localization
