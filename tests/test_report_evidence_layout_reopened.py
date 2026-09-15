"""Synthetic reductions of owner-reported R1-R4; no live approval or evidence."""
import io
from copy import deepcopy

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico.phase3_evidence_core_v1 import functional_qa_provider, platform_parity_provider
from nico.comprehensive_client_review_companion_v5 import substantive_review_sections
from nico.comprehensive_client_truth_final_v1 import _sync_executive
from nico.comprehensive_platform_parity_summary_v1 import canonical_platform_parity_status
from nico.comprehensive_four_phase_pdf_v1 import four_phase_target_page_index
from nico.comprehensive_pdf_layout_polish_v1 import _render_polished_toc_pdf
from nico.v2_dark_branded_cover_readiness_v4 import _truthful_executive_posture


@pytest.mark.parametrize("key", ["job_success_rate", "observed_job_success_rate"])
@pytest.mark.parametrize("rate", [0.0, 0.75, 1.0])
def test_retained_job_rate_is_localized_without_changing_observation(key, rate):
    from nico.comprehensive_ci_boundary_compat_v74 import ci_operational_truth_markdown
    canonical = {"report_language": "es-MX", "ci_operational_context": {key: rate}}
    before = deepcopy(canonical)
    output = ci_operational_truth_markdown(canonical, spanish=True)
    assert f"Tasa de éxito observada de trabajos: {rate * 100:.1f}%" in output
    assert "job success rate" not in output.casefold()
    assert canonical == before


def test_absent_job_rate_remains_absent_in_operational_companion():
    from nico.comprehensive_ci_boundary_compat_v74 import ci_operational_truth_markdown
    canonical = {"report_language": "es-MX", "ci_operational_context": {"jobs_observed": 0}}
    output = ci_operational_truth_markdown(canonical, spanish=True)
    assert "Tasa de éxito" not in output
    assert "Trabajos observados: 0" in output


@pytest.mark.parametrize("spanish", [False, True])
def test_ci_context_enums_have_reader_labels_and_preserve_source_values(spanish):
    from nico.comprehensive_ci_boundary_compat_v74 import ci_operational_truth_markdown, _format_value
    source = {"ci_operational_context": {"classification": "mutable_operational_trend",
              "score_effect": "none", "technical_score_effect": "none"}}
    before = deepcopy(source)
    output = ci_operational_truth_markdown(source, spanish=spanish)
    assert "mutable_operational_trend" not in output
    assert ("Contexto operativo mutable" if spanish else "Mutable operational context") in output
    assert ("Efecto en la puntuación: Ninguno" if spanish else "Score effect: None") in output
    assert _format_value("quoted_source", "none", spanish=spanish) == "none"
    assert source == before


def absent_canonical():
    return {"identity": {"repository": "example/synthetic", "commit_sha": "a" * 40},
            "assessment": {"technical_score": 93},
            "stage_summaries": [{"stage_id": stage, "status": "not_assessed",
                "evidence": ["Processing complete; assessment coverage and specialist review are reported separately."],
                "assessment_dimensions": {"execution_status": "complete", "substantive_coverage": "not_assessed",
                    "evidence_availability": "not_assessed", "full_coverage_claim": False}}
                for stage in ("functional_qa", "platform_parity")]}


@pytest.mark.parametrize("spanish", [False, True])
def test_score_wording_bounds_both_scores(spanish):
    text = _truthful_executive_posture(absent_canonical(), "93/100", "93/100", spanish=spanish)
    assert text.count("93/100") == 2
    assert "independently evidence-adjusted readiness" not in text
    assert ("no establece preparación operativa" if spanish else "does not establish operational readiness") in text


def test_canonical_workload_summary_uses_technical_score_meaning():
    from nico.comprehensive_candidate_volume_assurance_v2 import expose_candidate_workload_basis
    result = expose_candidate_workload_basis({"assessment": {"technical_score": 93, "evidence_adjusted_score": 93}})
    assert "readiness" not in result["summary"].casefold()
    assert "Evidence-Adjusted technical score is 93/100" in result["summary"]


@pytest.mark.parametrize("spanish", [False, True])
@pytest.mark.parametrize("score", [93, 0, None])
def test_companion_maturity_score_has_bounded_meaning_and_preserves_values(spanish, score):
    from nico.comprehensive_report_package import _markdown, _semantic_html
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation
    assessment = {"maturity_signal": {"presented_score": 93,
                  "evidence_readiness_score": score}}
    before = deepcopy(assessment)
    markdown = _markdown({}, assessment, [], "2026-09-15T00:00:00Z",
                         localize_presentation=_translate_presentation if spanish else None)
    label = "Puntuación técnica ajustada por evidencia" if spanish else "Evidence-adjusted technical score"
    value = ("Pendiente" if spanish else "Pending") if score is None else f"{score}/100"
    boundary = ("no establece preparación operativa, cobertura exhaustiva, revisión profesional independiente ni seguridad del despliegue"
                if spanish else "does not establish operational readiness, exhaustive coverage, independent professional review, or deployment safety")
    for output in (markdown, _semantic_html(markdown, "Synthetic score regression")):
        assert f"{label}: {value}" in output
        assert boundary in output
        assert "Evidence readiness:" not in output
        assert "Preparación de la evidencia:" not in output
    assert assessment == before


@pytest.mark.parametrize("provider", [functional_qa_provider, platform_parity_provider])
def test_absent_optional_inputs_are_not_reconciled(provider):
    result = provider({key: "synthetic" for key in (
        "run_id", "repository", "commit_sha", "evidence_ledger_id", "customer_id", "project_id")})
    assert result["assessment_dimensions"]["substantive_coverage"] == "not_assessed"
    assert "were reconciled" not in result["summary"]
    assert "not supplied" in result["summary"]


def test_repository_inventory_needs_retained_input_even_when_count_is_zero():
    context = {key: "synthetic" for key in (
        "run_id", "repository", "commit_sha", "evidence_ledger_id", "customer_id", "project_id")}
    assert functional_qa_provider(context)["functional_qa"]["repository_test_inventory_state"] == "not_supplied"
    context["prior_stage_results"] = {"repository_and_delivery_evidence": {
        "repository_evidence": {"architecture_evidence": {"test_path_count": 0}}}}
    result = functional_qa_provider(context)
    assert result["functional_qa"]["repository_test_inventory_state"] == "retained_observation"
    assert result["assessment_dimensions"]["substantive_coverage"] == "not_assessed"


@pytest.mark.parametrize("spanish", [False, True])
def test_parity_sections_do_not_promote_processing(spanish):
    source = absent_canonical()
    before = deepcopy(source)
    section = next(s for s in substantive_review_sections(source, spanish=spanish) if s["id"] == "platform_parity")
    assert ("Indicadores del repositorio evaluados" if spanish else "Repository indicators assessed") not in section["status"]
    assert ("no establecida" if spanish else "not established") in section["summary"]
    assert source == before


def test_processing_complete_alone_does_not_establish_repository_review():
    assert canonical_platform_parity_status({"stage_results": {"platform_parity": {"status": "complete"}}}) == "not_assessed"


def test_canonical_review_status_uses_retained_input_state():
    source = absent_canonical()
    _sync_executive(source)
    assert "Repository indicators assessed" not in source["assessment"]["review_section_statuses"]["platform_parity"]


@pytest.mark.parametrize("spanish", [False, True])
def test_phase_box_targets_last_contents_page(spanish):
    out = io.BytesIO(); c = canvas.Canvas(out)
    for title in ["Cover", "Tabla de contenido" if spanish else "Table of Contents",
                  "Tabla de contenido" if spanish else "Table of Contents", "Body"]:
        c.drawString(50, 740, title); c.showPage()
    c.save()
    assert four_phase_target_page_index(PdfReader(io.BytesIO(out.getvalue())), spanish=spanish) == 2


def test_frozen_historical_contents_keep_their_existing_phase_location():
    out = io.BytesIO(); c = canvas.Canvas(out)
    for lines in [["Cover"], ["Table of Contents", "FOUR-PHASE ASSESSMENT PROGRAM"], ["Table of Contents"]]:
        for i, line in enumerate(lines): c.drawString(50, 740 - i * 20, line)
        c.showPage()
    c.save()
    # A new source is paginated before its box is added. Retrieval of a frozen
    # source must not append a second box or move its historical contents.
    assert four_phase_target_page_index(PdfReader(io.BytesIO(out.getvalue())), spanish=False) == 1


@pytest.mark.parametrize("spanish", [False, True])
def test_contents_distribute_final_entry_with_its_group(spanish):
    records = [{"title": f"Synthetic entry {n:02}", "source_page_index": n + 1} for n in range(36)]
    pdf = _render_polished_toc_pdf(records, total_pages=40, toc_page_count=2, spanish=spanish)
    pages = PdfReader(io.BytesIO(pdf)).pages
    counts = [p.extract_text().count("Synthetic entry") for p in pages]
    assert sum(counts) == 36
    assert min(counts) >= 10


def test_owned_metric_lines_keep_values_with_readable_labels():
    from nico.comprehensive_client_surface_structure_cleanup_v1 import sanitize_client_rendered_stage
    lines = ["analyzer_execution_coverage: 100", "complexity_evidence.complexity_grades.A: 12"]
    result = sanitize_client_rendered_stage({"stage_id": "technical_analysis", "evidence": lines})
    text = " ".join(result["evidence"])
    assert "100" in text and "12" in text
    assert "analyzer_execution_coverage" not in text
    assert "complexity_evidence.complexity_grades.A" not in text
    literal = {"stage_id": "client_human_evidence_functional_qa", "evidence": lines}
    assert sanitize_client_rendered_stage(literal) == literal


@pytest.mark.parametrize("spanish", [False, True])
def test_scanner_tool_metric_labels_keep_tool_identity_and_counts(spanish):
    from nico.comprehensive_client_surface_structure_cleanup_v1 import sanitize_client_rendered_stage
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation
    lines = ["scanner_triage.finding_summary.by_tool.osv-scanner.raw: 22",
             "scanner_triage.finding_summary.by_tool.osv-scanner.review_required: 21"]
    stage = {"stage_id": "deep_scanner_triage", "evidence": lines}
    before = deepcopy(stage)
    result = sanitize_client_rendered_stage(stage)["evidence"]
    if spanish:
        result = [_translate_presentation(line) for line in result]
    assert result == (["osv-scanner — Candidatos sin procesar: 22", "osv-scanner — Candidatos que requieren revisión: 21"]
                      if spanish else ["osv-scanner — Raw candidates: 22", "osv-scanner — Review-required candidates: 21"])
    assert stage == before
    literal = {"stage_id": "client_human_evidence_functional_qa", "evidence": lines}
    assert sanitize_client_rendered_stage(literal) == literal


def test_planning_status_label_does_not_rewrite_literal_title():
    from nico.comprehensive_client_review_companion_v5 import _values
    records = [{"title": "Literal review_required title", "status": "review_required"}]
    before = deepcopy(records)
    assert _values(records) == ["Literal review_required title · Review required"]
    assert records == before


@pytest.mark.parametrize("spanish", [False, True])
def test_generated_human_evidence_state_is_readable_and_literal_input_is_preserved(spanish):
    from nico.comprehensive_human_evidence_report_v1 import _human_module_stage_specs
    snapshot = {"human_evidence": {"provided_module_ids": ["functional_qa"], "modules": {
        "functional_qa": {"evidence": {"test_cases": ["Literal supplied_unverified case"]}}}}}
    before = deepcopy(snapshot)
    specs = _human_module_stage_specs(snapshot, spanish=spanish)
    text = str(specs)
    assert ("Suministrada; sin verificación independiente" if spanish else "Supplied; not independently verified") in text
    assert "Literal supplied_unverified case" in text
    assert snapshot == before


@pytest.mark.parametrize("spanish", [False, True])
def test_new_complexity_fact_labels_explain_metric_without_changing_measurement(spanish):
    from nico.comprehensive_decision_content_restoration_v66 import _synthesized_complexity_findings
    from nico.comprehensive_spanish_exit_criteria_v88 import _translate_generated_complexity_contract
    hotspots = [{"path": "src/literal_name.ts", "line": 8, "name": "literal_name",
                 "cyclomatic_complexity": 36, "method": "typescript_compiler_ast"}]
    before = deepcopy(hotspots)
    finding = _synthesized_complexity_findings(hotspots, "a" * 40)[0]
    for field in ("fact", "evidence"):
        text = finding[field]
        if spanish:
            text = _translate_generated_complexity_contract(text)
        assert text is not None
        assert ("Complejidad ciclomática: 36 rutas independientes" if spanish else "Cyclomatic complexity: 36 independent paths") in text
        assert "typescript_compiler_ast" in text
        assert "cyclomatic_complexity=" not in text
    assert finding["path"] == "src/literal_name.ts"
    assert hotspots == before


@pytest.mark.parametrize("spanish", [False, True])
def test_missing_coverage_insertion_is_reader_facing(spanish):
    from nico.comprehensive_report_coverage_synchronization_v63 import _ensure_text_coverage_alias
    text, _, _ = _ensure_text_coverage_alias("Body", 100, html=False, required=True, spanish=spanish)
    assert ("Cobertura de ejecución de analizadores: 100%" if spanish else "Analyzer execution coverage: 100%") in text
    assert "analyzer_execution_coverage" not in text


def test_bound_repository_paths_establish_only_path_indicator_review():
    canonical = absent_canonical()
    canonical["identity"]["run_id"] = "synthetic-run"
    canonical["stage_results"] = {"platform_parity": {"evidence": {
        "source_indicator_state": "retained_observation", "source_indicator_paths": ["ios/View.swift"],
        "source_indicator_identity": deepcopy(canonical["identity"])}}}
    assert canonical_platform_parity_status(canonical) == "complete_repository_only"
    canonical["stage_results"]["platform_parity"]["evidence"]["source_indicator_identity"]["commit_sha"] = "b" * 40
    assert canonical_platform_parity_status(canonical) == "not_assessed"


@pytest.mark.parametrize("scope", ["functional_qa", "desktop", "mobile", "english", "es_mx"])
def test_real_retained_observation_survives_absent_optional_fields(scope):
    canonical = absent_canonical()
    canonical["production_acceptance"] = {scope: {"execution_id": "synthetic-retained-execution"}}
    canonical["retained_runtime_executions"] = {"synthetic-retained-execution": {
        "kind": "actual", "performed": True, "scope": scope,
        "repository": "example/synthetic", "commit_sha": "a" * 40,
        "evidence_reference": "synthetic://result", "result": "fail",
        "retained_results": ["synthetic regression result"],
        "observer": "synthetic observer", "observed_at": "2026-09-15T00:00:00Z"}}
    section_id = "functional_qa" if scope == "functional_qa" else "platform_parity"
    section = next(s for s in substantive_review_sections(canonical, spanish=False) if s["id"] == section_id)
    assert section["runtime_observation_established"] is True
    assert section["independently_verified"] is False


def test_optional_qa_omit_supply_clear_and_partial_inputs():
    context = {key: "synthetic" for key in (
        "run_id", "repository", "commit_sha", "evidence_ledger_id", "customer_id", "project_id")}
    absent = functional_qa_provider(context)
    module = {"status": "complete", "verification_status": "verified", "evidence": {"test_cases": ["Sign in"]}}
    context["human_evidence"] = {"modules": {"functional_qa": module}}
    cases_only = functional_qa_provider(context)
    assert "result text was not supplied" in cases_only["summary"]
    assert cases_only["functional_qa"]["runtime_evidence_state"] == "supplied_unverified"
    module["evidence"]["observed_results"] = ["Sign in: passed"]
    assert "test cases and result text" in functional_qa_provider(context)["summary"]
    module["evidence"] = {"observed_results": ["Sign in: passed"]}
    assert "test cases were not supplied" in functional_qa_provider(context)["summary"]
    module["evidence"] = {}
    assert functional_qa_provider(context)["summary"] == absent["summary"]
    module["excluded"] = True
    excluded = functional_qa_provider(context)
    assert "excluded from scope" in excluded["summary"]
    assert excluded["assessment_dimensions"]["substantive_coverage"] == "excluded"


def test_absent_incidents_do_not_become_reconciled_history():
    from nico.phase3_planning_synthesis_v1 import historical_trends_provider
    context = {key: "synthetic" for key in (
        "run_id", "repository", "commit_sha", "evidence_ledger_id", "customer_id", "project_id")}
    result = historical_trends_provider(context)
    assert "were reconciled" not in result["summary"]
    assert "Incident evidence was not supplied" in result["summary"]
    assert result["historical_trends"]["operational_history_state"] == "not_supplied"


@pytest.mark.parametrize("spanish", [False, True])
def test_phase_box_keeps_readable_type_and_all_cells(spanish):
    from nico.comprehensive_four_phase_pdf_v1 import _overlay
    pdf = _overlay(absent_canonical(), spanish, (612, 792))
    sizes = []
    page = PdfReader(io.BytesIO(pdf)).pages[0]
    page.extract_text(visitor_text=lambda text, cm, tm, font, size: sizes.append(size) if text.strip() else None)
    assert min(sizes) >= 6.8


@pytest.mark.parametrize("spanish", [False, True])
def test_ci_context_keys_are_reader_labels(spanish):
    from nico.comprehensive_ci_boundary_compat_v74 import _label
    for key in ("classification", "configuration_maturity_scored_separately", "non_success_runs",
                "required_check_health_reported_separately", "score_effect", "technical_score_effect"):
        label = _label(key, spanish=spanish)
        assert "`" not in label and "_" not in label


@pytest.mark.parametrize("fields", [{}, {"test_cases": ["Sign in"]}, {"observed_results": ["Sign in: passed"]}, {"test_cases": ["Sign in"], "observed_results": ["Sign in: passed"]}])
def test_qa_input_narratives_have_canonical_spanish_translation(fields):
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation_field
    context = {key: "synthetic" for key in (
        "run_id", "repository", "commit_sha", "evidence_ledger_id", "customer_id", "project_id")}
    context["human_evidence"] = {"modules": {"functional_qa": {"evidence": fields}}}
    text = functional_qa_provider(context)["summary"]
    translated = _translate_presentation_field(text, "summary")
    assert translated != text
    assert "Supplied" not in translated and "were not supplied" not in translated


def test_absent_delivery_history_does_not_claim_provider_review():
    from nico.comprehensive_native_providers import delivery_process_provider
    context = {key: 'synthetic' for key in ('run_id', 'repository', 'commit_sha', 'evidence_ledger_id', 'customer_id', 'project_id')}
    result = delivery_process_provider(context)
    assert 'were reviewed' not in result['summary']
    assert 'not assessed' in result['summary']


def test_absent_workflow_history_is_not_described_as_retained_outcomes():
    canonical = absent_canonical()
    canonical['ci_operational_context'] = {'successful_runs': 0, 'non_success_runs': 0}
    section = next(s for s in substantive_review_sections(canonical, spanish=False) if s['id'] == 'historical_trends_and_change_failure')
    assert 'No workflow outcome observations were retained' in section['summary']


def test_genuine_delivery_counts_survive_canonical_projection():
    from nico.comprehensive_report_package import _stage_summary
    from nico.comprehensive_client_truth_canonical_v2 import _normalize_stage_truth
    stage = _stage_summary('developer_delivery_process', {'status': 'complete', 'evidence': {'commits_returned': 2, 'pull_requests_returned': 3, 'jobs_observed': 4}})
    result = _normalize_stage_truth({'stage_summaries': [stage]})['stage_summaries'][0]
    assert result['commits_returned'] == 2
    assert result['pull_requests_returned'] == 3
    assert result['jobs_observed'] == 4
    assert 'Retained commit' in result['summary']
    assert 'does not establish' in result['summary']


@pytest.mark.parametrize("requirements,constraints", [(False, False), (True, False), (False, True), (True, True)])
def test_roadmap_narrative_tracks_retained_optional_inputs_and_clear(requirements, constraints):
    from nico.phase3_planning_synthesis_v1 import roadmap_provider
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation
    context = {key: "synthetic" for key in (
        "run_id", "repository", "commit_sha", "evidence_ledger_id", "customer_id", "project_id")}
    context["prior_stage_results"] = {
        "requirements_traceability": {"requirements_traceability": {"mappings":
            [{"requirement_id": "REQ-LITERAL", "requirement": "source: verified"}] if requirements else []}},
        "stakeholder_and_business_alignment": {"stakeholder_alignment": {"constraints":
            ["source: reviewed"] if constraints else []}}}
    before = deepcopy(context)
    result = roadmap_provider(context)
    text = result["summary"]
    assert ("Retained requirement mappings were included." if requirements else
            "No requirement mappings were retained.") in text
    assert ("Retained stakeholder constraints were included." if constraints else
            "No stakeholder constraints were retained.") in text
    assert "without creating commitments" in text
    assert result["roadmap"][0]["requirements"] == (["REQ-LITERAL"] if requirements else [])
    assert result["roadmap"][0]["constraints"] == (["source: reviewed"] if constraints else [])
    assert context == before
    spanish = _translate_presentation(text)
    assert "sin crear compromisos" in spanish
    assert "were retained" not in spanish and "were included" not in spanish
    from pathlib import Path
    ui = Path("apps/web/app/assessment/AssessmentSpanishLocalization.ts").read_text()
    assert f'["{text.lower()}",' in ui
    context["prior_stage_results"] = {}
    cleared = roadmap_provider(context)
    assert "No requirement mappings were retained." in cleared["summary"]
    assert "No stakeholder constraints were retained." in cleared["summary"]
    assert not cleared["roadmap"][0]["requirements"] and not cleared["roadmap"][0]["constraints"]


def test_source_table_enum_labels_preserve_paths_and_source_values():
    from nico.comprehensive_report_package import _source_cell
    assert _source_cell('source_module', spanish=False) == 'Source module'
    assert _source_cell('http_call', spanish=False) == 'HTTP call'
    assert _source_cell('outbound_network_destination_unresolved', spanish=False) == 'Outbound network destination unresolved'
    assert _source_cell('declared_container_configuration', spanish=False) == 'Declared container configuration'
    assert _source_cell('source_module', spanish=True) == 'módulo de código'
    assert _source_cell('src/source_module.py', spanish=False) == 'src/source_module.py'


def test_work_package_labels_preserve_machine_gap_references():
    from nico.comprehensive_finding_roadmap_v1 import bind_final_finding_roadmap
    source = {'identity': {'run_id': 'synthetic', 'repository': 'fixture/repo', 'commit_sha': 'a'*40, 'evidence_ledger_id': 'synthetic-ledger'},
              'assessment': {}, 'canonical_findings': [], 'review_candidate_summary': {'review_required_total': 3},
              'stage_summaries': [{'stage_id': 'six_month_roadmap'}]}
    before = deepcopy(source)
    result = bind_final_finding_roadmap(source, raw_stages={})
    assert result['roadmap'][0]['source_refs'][0]['surface'] == 'review_candidate_summary'
    assert ' | Candidate review summary | ' in '\n'.join(result['stage_summaries'][0]['evidence'])
    assert source == before


@pytest.mark.parametrize('spanish', [False, True])
def test_historical_workflow_timeout_uses_reader_label(spanish):
    from nico.comprehensive_ci_boundary_compat_v74 import _historical_line
    source = {'ci_operational_context': {'outcome_taxonomy': {'timed_out': 2}, 'workflow_run_count': 2}}
    before = deepcopy(source)
    text = _historical_line(source, spanish=spanish)
    assert ('agotadas por tiempo=2' if spanish else 'timed out=2') in text
    assert 'timed_out=' not in text and 'agotadas_por_tiempo=' not in text
    assert source == before


def test_scanner_provenance_reader_labels_preserve_retained_record_and_digests():
    from nico.comprehensive_release_provenance_v1 import _provenance_lines
    source = {'scanner_execution_evidence': {'scanner_records': [{'scanner_name': 'fixture',
        'execution_status': 'completed', 'execution_evidence_verified': True,
        'inapplicability_evidence_verified': False, 'raw_artifact': {'sha256': 'a'*64},
        'execution_provenance': {'execution_receipt': {'receipt_sha256': 'b'*64,
                               'status': 'retained_receipt_integrity_verified'}}, 'configuration': {}}]}}
    before = deepcopy(source)
    text = '\n'.join(value for _,value in _provenance_lines(source))
    assert 'execution evidence verified=True' in text
    assert 'full configuration verified=False' in text
    assert 'retained receipt integrity verified' in text
    assert 'execution_evidence_verified=' not in text
    assert 'a'*64 in text and 'b'*64 in text and source == before


def test_candidate_prose_labels_keep_numeric_counts_and_machine_dispositions():
    from types import SimpleNamespace
    from nico.comprehensive_report_content_render_v66 import _candidate_stage
    source = {'review_candidate_summary': {'raw_total': 2, 'review_required_total': 2,
              'by_category': {'dependency': {'raw': 2, 'material': 0, 'review_required': 2,
                  'excluded_test_only': 0, 'approved_or_nonblocking': 0}}},
              'review_candidate_register': [{'candidate_id': 'C-LITERAL', 'disposition': 'review_required',
                                           'title': 'literal supplied_unverified'}]}
    before = deepcopy(source)
    result = _candidate_stage(source, SimpleNamespace(_stage=lambda *args, **kw: kw))
    text = '\n'.join(result['evidence'] + result['findings'])
    assert 'confirmed material=0' in text and 'review required=2' in text
    assert 'disposition=review required' in text
    assert 'literal supplied_unverified' in text
    assert source == before
