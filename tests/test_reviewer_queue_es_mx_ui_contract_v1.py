import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "apps/web/app/operations/reviewer-queue/ReviewerQueue.tsx"
BROWSER = ROOT / "apps/web/app/operations/reviewer-queue/ReviewQueueBrowser.tsx"
WORK_PANEL = ROOT / "apps/web/app/operations/reviewer-queue/ReviewWorkPanel.tsx"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def direct_jsx_text(source_text: str) -> set[str]:
    """Return literal JSX text nodes; expressions and canonical JSON are excluded."""
    return {
        value.strip()
        for value in re.findall(r">([^<>{}\n]+)<", source_text)
        if value.strip()
    }


def test_es_mx_is_selected_from_query_and_updates_document_language_and_title() -> None:
    queue = source(QUEUE)
    browser = source(BROWSER)

    for component in (queue, browser):
        assert 'type Locale = "en" | "es-MX"' in component
        assert 'get("lang") === "es-MX"' in component
        assert "document.documentElement.lang = requestedLocale" in component
        assert '"Espacio de revisión humana | NICO"' in component


def test_known_reviewer_queue_copy_has_professional_mexican_spanish_rendering() -> None:
    queue = source(QUEUE)
    browser = source(BROWSER)

    queue_pairs = {
        "Expandable deterministic review clusters": "Grupos deterministas de revisión expandibles",
        "Open an exact terminal run": "Abrir una ejecución terminal exacta",
        "Queue integrity check failed closed.": "La verificación de integridad de la cola falló de forma cerrada.",
        "Canonical parity verified.": "Paridad canónica verificada.",
        "Individual attention": "Atención individual",
        "Deterministic grouped work units": "Unidades de trabajo deterministas agrupadas",
        "Complete retained canonical candidate record": "Registro canónico completo del candidato conservado",
        "Expand candidate": "Expandir candidato",
        "Collapse cluster": "Contraer grupo",
    }
    browser_pairs = {
        "Final approval blocked": "Aprobación final bloqueada",
        "Authorized reviewer": "Revisor autorizado",
        "Human disposition": "Disposición humana",
        "Quality-control sampling": "Muestreo de control de calidad",
        "Clear filters": "Limpiar filtros",
        "No canonical candidates match the selected filters.": "Ningún candidato canónico coincide con los filtros seleccionados.",
        "Clusters summarize homogeneous review work.": "Los grupos resumen trabajo homogéneo de revisión.",
    }

    for english, spanish in queue_pairs.items():
        assert english in queue
        assert spanish in queue
    for english, spanish in browser_pairs.items():
        assert english in browser
        assert spanish in browser


def test_es_mx_ui_has_no_unlocalized_literal_text_nodes_except_technical_allowlist() -> None:
    # Canonical technical literals intentionally remain unchanged. All other visible
    # authored copy must flow through locale-aware expressions rather than raw JSX.
    allowlist = {"Commit", "QC", ":"}
    observed = direct_jsx_text(source(QUEUE)) | direct_jsx_text(source(BROWSER)) | direct_jsx_text(source(WORK_PANEL))
    assert observed <= allowlist


def test_locale_switch_preserves_exact_run_query_and_other_url_state() -> None:
    queue = source(QUEUE)
    work_panel = source(WORK_PANEL)

    for component in (queue, work_panel):
        assert "const target = new URL(window.location.href)" in component
        assert 'target.searchParams.set("lang", nextLocale)' in component
        assert 'target.searchParams.set("run_id", runId.trim())' in component
        assert "`${target.pathname}${target.search}${target.hash}`" in component
    assert "setLocale(locale ===" not in work_panel


def test_localization_does_not_mutate_canonical_candidate_values_enums_or_json() -> None:
    queue = source(QUEUE)
    browser = source(BROWSER)

    assert "JSON.stringify(candidate, null, 2)" in queue
    assert "JSON.stringify(candidate, null, 2)" in browser
    assert "JSON.stringify(cluster, null, 2)" in browser
    assert "text(candidate.candidate_id)" in browser
    assert "text(candidate.primary_review_queue)" in browser
    assert "text(candidate.technical_triage_verdict)" in browser
    assert "searchHaystack(candidate)" in browser
    assert "setQueue(item.value)" in browser
    assert '<option key={value}>{value}</option>' in browser


def test_review_work_controls_localize_visible_enum_labels_without_mutating_values() -> None:
    panel = source(WORK_PANEL)

    for value, english, spanish in (
        ("confirmed", "confirmed", "Confirmado"),
        ("false_positive", "false positive", "Falso positivo"),
        ("not_applicable", "not applicable", "No aplica"),
        ("accepted_risk", "accepted risk", "Riesgo aceptado"),
        ("needs_more_evidence", "needs more evidence", "Requiere más evidencia"),
        ("agree", "agree", "De acuerdo"),
        ("disagree", "disagree", "En desacuerdo"),
    ):
        assert f'value: "{value}"' in panel
        assert f'en: "{english}"' in panel
        assert f'es: "{spanish}"' in panel

    assert "DISPOSITIONS.map" in panel
    assert "QC_OUTCOMES.map" in panel
    assert "disposition," in panel
    assert "qc_outcome: qcOutcome" in panel
    assert '<option value="confirmed">confirmed</option>' not in panel
    assert '<option value="agree">agree</option>' not in panel


def test_review_work_empirical_copy_and_states_are_localized() -> None:
    panel = source(WORK_PANEL)

    for phrase in (
        "NICO COMPREHENSIVE · FASE 2",
        "Estado",
        "Horas combinadas de especialistas",
        "≤ 4 horas verificadas",
        "Eventos de auditoría",
        "Aún no medido",
        "Verificado dentro de cuatro horas",
        "Medido en más de cuatro horas",
    ):
        assert phrase in panel

    assert 'not_yet_measured: "Aún no medido"' in panel
    assert "empiricalStatus(empirical.status, locale)" in panel
    assert "Estado técnico: ${status}" in panel
    assert "? copy.yes : copy.no" in panel
    assert '<dt>Status</dt>' not in panel
    assert 'String(empirical.status || "not_yet_measured")' not in panel


def test_review_work_es_mx_errors_do_not_surface_arbitrary_english_backend_detail() -> None:
    panel = source(WORK_PANEL)

    assert "parseResponse(response, locale)" in panel
    assert "errorMessage(caught, locale)" in panel
    assert "No fue posible completar la solicitud protegida de trabajo de revisión" in panel
    assert '/^[A-Z0-9_.-]+$/' in panel
    assert 'if (locale === "es-MX")' in panel
