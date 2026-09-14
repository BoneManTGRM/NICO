"""Missing operational evidence must publish as unavailable, never as measured zero."""
from copy import deepcopy

import pytest

from nico import v2_premium_report_renderer as renderer
from nico.comprehensive_report_content_render_v66 import _ci_operational_stage
from nico.comprehensive_spanish_canonical_report_v87 import (
    _localize_tree,
    _translate_presentation_field,
)


METRICS = (
    ("successful_runs", "Successful workflow runs", "Ejecuciones exitosas de flujos de trabajo"),
    ("non_success_runs", "Non-success workflow runs", "Ejecuciones no exitosas de flujos de trabajo"),
    ("jobs_observed", "Jobs observed", "Trabajos observados"),
    ("job_success_rate", "Observed job success rate", "Tasa de éxito observada de trabajos"),
    ("deployments_observed", "Deployments observed", "Despliegues observados"),
    ("successful_deployments", "Successful deployments", "Despliegues exitosos"),
    ("non_success_deployments", "Non-success deployments", "Despliegues no exitosos"),
    ("historical_genuine_failure_rate", "Historical genuine-failure rate", "Tasa histórica de fallos reales"),
    ("required_check_health", "Required-check health", "Estado de las verificaciones requeridas"),
    ("assessed_commit_required_check_health", "Assessed-commit required-check health", "Estado de las verificaciones requeridas del commit evaluado"),
    ("current_default_branch_required_check_health", "Current default-branch required-check health", "Estado de las verificaciones requeridas de la rama predeterminada actual"),
)


def test_installed_current_copy_pass_preserves_complete_metric_translation():
    from nico import comprehensive_spanish_canonical_report_v87 as spanish
    from nico.comprehensive_current_report_truth_parity_v1 import (
        install_comprehensive_current_report_truth_parity_v1,
    )
    from nico.comprehensive_spanish_current_copy_worker_v98 import (
        install_comprehensive_spanish_current_copy_worker_v98,
    )
    from nico.v2_production_authority import _reassert_terminal_report_language_authority

    install_comprehensive_current_report_truth_parity_v1()
    _reassert_terminal_report_language_authority()
    install_comprehensive_spanish_current_copy_worker_v98()
    for _, english, label in METRICS:
        assert spanish._translate_presentation_field(
            f"{english}: Unavailable.", "evidence",
        ) == f"{label}: no disponible."


def test_metric_translation_preserves_multiline_values_and_line_endings():
    from nico.comprehensive_spanish_current_copy_worker_v98 import localize_current_report_copy_v98

    value = "Successful workflow runs: 0.\r\nJobs observed: Unavailable.\n"
    assert localize_current_report_copy_v98(value) == (
        "Ejecuciones exitosas de flujos de trabajo: 0.\r\n"
        "Trabajos observados: no disponible.\n"
    )


@pytest.mark.parametrize("rate", ["0%", "12.5%", "100%", "100.0%"])
def test_observed_job_percentage_survives_installed_spanish_publication(rate):
    from nico.comprehensive_spanish_current_copy_worker_v98 import localize_current_report_copy_v98

    # The retained production failure was exactly this metric with 100%.
    # Preserve the supplied unit and value, without changing canonical evidence.
    canonical = {"ci_operational_context": {"job_success_rate": rate}}
    before = deepcopy(canonical)
    stage = _ci_operational_stage(canonical, renderer)
    line = f"Observed job success rate: {rate}."
    expected = f"Tasa de éxito observada de trabajos: {rate}."
    assert line in stage["evidence"]
    assert _translate_presentation_field(line, "evidence") == expected
    assert localize_current_report_copy_v98(line) == expected
    assert expected in _localize_tree(stage)["evidence"]
    assert canonical == before


@pytest.mark.parametrize("missing", [None, ""])
@pytest.mark.parametrize("key,english,spanish", METRICS)
def test_generated_missing_ci_metric_has_explicit_spanish_availability(key, english, spanish, missing):
    canonical = {"ci_operational_context": {key: missing}}
    before = deepcopy(canonical)
    stage = _ci_operational_stage(canonical, renderer)
    line = next(line for line in stage["evidence"] if line.startswith(english + ":"))
    assert line == f"{english}: Unavailable."
    assert _translate_presentation_field(line, "evidence") == f"{spanish}: no disponible."
    assert canonical == before


@pytest.mark.parametrize("key,english,spanish", METRICS[:8])
def test_boolean_is_not_a_measured_count_or_rate(key, english, spanish):
    stage = _ci_operational_stage({"ci_operational_context": {key: False}}, renderer)
    line = f"{english}: Unavailable."
    assert line in stage["evidence"]
    assert _translate_presentation_field(line, "evidence") == f"{spanish}: no disponible."


@pytest.mark.parametrize("number", [0, 0.25, 7])
@pytest.mark.parametrize("key,english,spanish", METRICS[:8])
def test_generated_numeric_ci_metric_preserves_supported_number(key, english, spanish, number):
    stage = _ci_operational_stage({"ci_operational_context": {key: number}}, renderer)
    line = next(line for line in stage["evidence"] if line.startswith(english + ":"))
    assert _translate_presentation_field(line, "evidence").rstrip(".") == f"{spanish}: {number}"


def test_sparse_operational_stage_localizes_all_fields_without_mutating_evidence():
    canonical = {"ci_operational_context": {"successful_runs": 0}}
    before = deepcopy(canonical)
    stage = _ci_operational_stage(canonical, renderer)
    localized = _localize_tree(stage)
    assert localized["stage_id"] == stage["stage_id"]
    assert localized["status"] == stage["status"]
    for key, english, spanish in METRICS:
        expected = "0" if key == "successful_runs" else "no disponible"
        assert f"{spanish}: {expected}." in localized["evidence"]
    assert canonical == before


@pytest.mark.parametrize("line", [
    "Historical genuine-failure rate: pending review",
    "Historical genuine-failure rate: Unavailable. Additional context",
    "Assessed-commit required-check health: invented_success.",
    "Historical workflow outcome classes: success=; genuine_failure=1.",
    "Jobs observed: claimed successful.",
    "Successful workflow runs: Unavailable. Additional context",
    "Required-check health: 0.",
    "Observed job success rate: 100%. Additional context",
    "Observed job success rate: claimed successful%.",
    "Observed job success rate: -1%.",
    "Observed job success rate: 101%.",
    "Jobs observed: 100%.",
])
def test_unrecognized_structured_prose_is_still_rejected(line):
    with pytest.raises(ValueError, match="unrecognized Spanish presentation contract"):
        _translate_presentation_field(line, "evidence")


@pytest.mark.parametrize("health,spanish", [
    ("green", "en verde"), ("not_green", "no verde"),
    ("unknown", "desconocido"), ("not_observed", "no observado"),
])
def test_retained_check_health_keeps_its_actual_state(health, spanish):
    for _, english, label in METRICS[8:]:
        assert _translate_presentation_field(f"{english}: {health}.", "evidence") == f"{label}: {spanish}."


@pytest.mark.parametrize("health,english,spanish", [
    (True, "green", "en verde"), (False, "not_green", "no verde"),
])
def test_recorded_default_branch_health_boolean_is_not_missing(health, english, spanish):
    stage = _ci_operational_stage({"ci_operational_context": {
        "current_default_branch_required_check_health": health,
    }}, renderer)
    line = f"Current default-branch required-check health: {english}."
    assert line in stage["evidence"]
    assert _translate_presentation_field(line, "evidence") == (
        f"Estado de las verificaciones requeridas de la rama predeterminada actual: {spanish}."
    )


def test_historical_outcome_counts_keep_zero_and_localize_their_class_names():
    canonical = {"ci_operational_context": {
        "workflow_outcome_classes": {"success": 0, "genuine_failure": 1},
    }}
    stage = _ci_operational_stage(canonical, renderer)
    line = "Historical workflow outcome classes: success=0; genuine_failure=1."
    assert line in stage["evidence"]
    assert _translate_presentation_field(line, "evidence") == (
        "Clases históricas de resultados de los flujos de trabajo: exitosas=0; fallos reales=1."
    )
    assert canonical["ci_operational_context"]["workflow_outcome_classes"] == {"success": 0, "genuine_failure": 1}


def test_full_spanish_finalizer_publishes_sparse_operational_metrics():
    import base64
    import io
    import re

    from pypdf import PdfReader
    from nico.phase9_comprehensive_report_integration_v1 import finalize_report_package
    from nico.v2_production_authority import _reassert_terminal_report_language_authority
    from tests.test_phase9_comprehensive_report_integration_v1 import _result

    fixture = _result()
    canonical = fixture["report_package"]["json"]
    canonical.update(report_language="es-MX", locale="es-MX")
    canonical["identity"]["report_language"] = "es-MX"
    # Explicit observed outcome counts belong to this fixture. Other compact CI
    # metrics remain absent and are covered field by field in the stage tests.
    operational = {"successful_runs": 0, "workflow_outcome_classes": {"success": 0}}
    canonical["ci_operational_context"] = deepcopy(operational)
    # Production reinstalls the terminal renderers immediately before publication.
    _reassert_terminal_report_language_authority()
    package = finalize_report_package(fixture)["report_package"]
    assert package["json"]["ci_operational_context"]["successful_runs"] == 0
    assert package["json"]["ci_operational_context"].get("historical_genuine_failure_rate") is None
    pdf = PdfReader(io.BytesIO(base64.b64decode(package["pdf_base64"])))
    text = re.sub(r"\s+", " ", " ".join(page.extract_text() for page in pdf.pages))
    # This finalizer consolidates operational context rather than repeating each
    # intermediate metric line. It must publish a readable Spanish report and keep
    # the underlying zero/absence distinction; exact lines are tested above.
    assert "Preparación operativa y salud histórica de CI/CD" in text
    assert "no se trata como aprobado" in text
    assert "Historical genuine-failure rate: Unavailable" not in text
    assert "Jobs observado" not in text
    assert ": ." not in text
