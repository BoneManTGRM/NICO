"""Bounded, allowlisted console classifications; never acceptance decisions."""


def classification(value, allowed):
    if value is None:
        return 'none'
    return value if type(value) is str and value in allowed else 'other'


def object_value(value):
    return value if type(value) is dict else {}


def scanner_failure_diagnostic(scan):
    scan = object_value(scan)
    return {
        'schema': 'nico.scanner-failure-diagnostic.v1',
        'status': classification(scan.get('status'), ('queued', 'running', 'complete', 'unavailable', 'failed', 'error', 'cancelled', 'blocked', 'partial')),
        'current_stage': classification(scan.get('current_stage'), ('execution_limited', 'complete', 'snapshot_verification_failed', 'worker_cleanup_unconfirmed', 'failed', 'error', 'queued', 'running')),
        'snapshot_match': scan.get('snapshot_match') is True,
        'execution_limit_present': bool(object_value(scan.get('execution_limit'))),
        'execution_limit_reason': classification(object_value(scan.get('execution_limit')).get('reason'), ('repository_size_limit_exceeded', 'repository_size_unverified')),
        'tools_run_present': type(scan.get('tools_run')) is list and bool(scan['tools_run']),
        'failed_tools_present': type(scan.get('failed_tools')) is list and bool(scan['failed_tools']),
        'timed_out_tools_present': type(scan.get('timed_out_tools')) is list and bool(scan['timed_out_tools']),
        'unavailable_tools_present': type(scan.get('unavailable_tools')) is list and bool(scan['unavailable_tools']),
    }


def runtime_operation_classification(value):
    import re
    allowed = ('runtime-functional-setup', 'runtime-functional', 'runtime-functional-results',
        'runtime-fuzz-corpus-stage', 'runtime-fuzz-configure', 'runtime-fuzz-build', 'runtime-fuzz-campaign')
    allowed += tuple('runtime-' + kind + '-' + suffix for kind in ('address', 'undefined')
        for suffix in ('configure', 'build', 'discover', 'tests', 'test-log', 'resources', 'junit'))
    allowed += tuple('runtime-reclaim-' + phase for phase in ('baseline', 'address', 'undefined'))
    if type(value) is str and len(value) <= 64 and re.fullmatch(r'runtime-fuzz-replay-[0-9]+', value):
        return 'runtime-fuzz-replay'  # Never print an arbitrary operation ID.
    return classification(value, allowed)


def collection_failure_diagnostic(receipt):
    receipt = object_value(receipt)
    probe = object_value(receipt.get('probe'))
    stage = object_value(probe.get('project_static_stage'))
    statuses = ('UNPROVEN', 'BASELINE_EXECUTED', 'CONFIGURATION_CAPTURED')
    probe_errors = tuple('worker_configuration_probe_' + suffix for suffix in (
        'static_incomplete', 'static_failed', 'runtime_incomplete', 'native_tests_failed',
        'compiler_failed', 'compiler_evidence_invalid', 'compiler_incomplete',
        'snapshot_failed', 'snapshot_invalid', 'snapshot_capacity_exceeded', 'interrupted', 'failed'))
    static_errors = tuple('worker_project_static_stage_' + suffix for suffix in (
        'analysis_failed', 'analysis_incomplete', 'artifact_reference_invalid', 'artifact_retention_failed',
        'boundary_invalid', 'cleanup_failed', 'contract_invalid', 'deadline', 'environment_failed',
        'environment_flag_invalid', 'failed', 'fallback_failed', 'image_mismatch', 'interrupted',
        'operation_failed', 'private_invalid', 'restore_mismatch', 'source_mismatch', 'storage_invalid'))
    runtime = object_value(probe.get('runtime_summary'))
    observed = (receipt.get('status'), receipt.get('stage'), probe.get('status'), probe.get('error'))
    return {
        'schema': 'nico.collection-failure-diagnostic.v1',
        'receipt_status': classification(receipt.get('status'), statuses),
        'receipt_stage': classification(receipt.get('stage'), ('completed', 'execution_unproven', 'configuration_unproven')),
        'probe_status': classification(probe.get('status'), statuses),
        'probe_error': classification(probe.get('error'), probe_errors),
        'status_combination_allowed': observed in (
            ('BASELINE_EXECUTED', 'completed', 'BASELINE_EXECUTED', None),
            ('UNPROVEN', 'execution_unproven', 'UNPROVEN', 'worker_configuration_probe_runtime_incomplete')),
        'static_stage_present': bool(stage),
        'static_complete': stage.get('complete') is True,
        'static_error': classification(stage.get('error'), static_errors),
        'static_analysis_complete': object_value(stage.get('analysis')).get('complete') is True,
        'static_boundary_verified': stage.get('boundary_verified') is True,
        'static_cleanup_verified': stage.get('cleanup_verified') is True,
        'runtime_complete': runtime.get('complete') is True,
        'runtime_error': classification(runtime.get('error'), tuple('worker_runtime_' + suffix for suffix in (
            'functional_failed', 'artifact_unavailable', 'sanitizer_failed', 'fuzz_failed',
            'reclamation_failed', 'deadline', 'failed'))),
        'runtime_failure_operation': runtime_operation_classification(runtime.get('failure_operation')),
    }


_RENDERER_EXCEPTIONS = (
    'LayoutError', 'KeyError', 'ValueError', 'TypeError', 'MemoryError', 'TimeoutError',
    'RuntimeError', 'WorkerProcessExit', 'WorkerPayloadError', 'ImportError',
    'ModuleNotFoundError', 'UnicodeEncodeError', 'UnicodeDecodeError', 'OSError',
    'PermissionError', 'FileNotFoundError', 'RecursionError', 'AttributeError')


def provider_failure_classification(value):
    templates = {
        'PDF export unavailable: ': 'pdf_export_unavailable',
        'Decision-grade PDF export unavailable: ': 'decision_grade_pdf_export_unavailable',
        'Decision-grade contract unavailable: ': 'decision_grade_contract_unavailable',
        'Decision-grade backlog export unavailable: ': 'decision_grade_backlog_export_unavailable',
        'Historical delta unavailable: ': 'historical_delta_unavailable',
    }
    if type(value) is str:
        for prefix, category in templates.items():
            if value.startswith(prefix):
                # Return only predefined labels; never the exception message/type suffix.
                return category, classification(value[len(prefix):], _RENDERER_EXCEPTIONS)
    return 'none' if value is None else 'other', 'none'


def v2_publication_failure_diagnostic(value):
    value = object_value(value)
    error = value.get('error')
    codes = {
        'spanish_presentation_preflight_failed:': 'spanish_presentation_preflight_failed',
        'missing Spanish presentation translation for': 'spanish_translation_missing',
        'unrecognized Spanish presentation contract:': 'spanish_presentation_contract_unrecognized',
        'canonical Spanish PDF renderer failed:': 'spanish_pdf_renderer_failed',
        'premium PDF renderer failed:': 'premium_pdf_renderer_failed',
        'report package is missing canonical JSON': 'canonical_json_missing',
        'v2 publication did not bind a canonical truth hash': 'canonical_truth_hash_missing',
        'v2 publication did not produce the canonical findings CSV': 'findings_csv_missing',
        'Authoritative PDF contains control-character glyphs:': 'pdf_control_character_glyphs',
        'final Spanish premium PDF omitted pending-approval semantics': 'spanish_pending_approval_missing',
        'final premium PDF omitted required identity text:': 'pdf_identity_text_missing',
        'technical scorecard page was not found for safe replacement;': 'pdf_scorecard_missing',
    }
    category = 'none' if error is None else 'other'
    if type(error) is str:
        for prefix, code in codes.items():
            if error.startswith(prefix):
                category = code
                break
    result = {'error_type': classification(value.get('error_type'), _RENDERER_EXCEPTIONS),
        'error_category': category, 'canonical_only_source_used': value.get('canonical_only_source_used') is True}
    # Reuse existing strict cap validation, then discard all identity/hash fields.
    from nico.pdf_cap_failure_diagnostics import sanitize_pdf_cap_diagnostic
    cap = sanitize_pdf_cap_diagnostic(value.get('pdf_cap_diagnostic'))
    if cap is not None:
        result['pdf_cap'] = {key: cap[key] for key in (
            'failure_reason', 'page_limit', 'base_pages', 'retained_body_pages_before_reflow',
            'retained_body_pages_after_reflow', 'register_pages', 'gate_pages', 'review_pages',
            'ci_boundary_pages', 'human_evidence_pages', 'required_pages', 'total_pages', 'reflow_attempted')}
    if category == 'spanish_translation_missing':
        from nico.spanish_translation_failure_diagnostic import spanish_translation_failure_diagnostic
        result['translation'] = spanish_translation_failure_diagnostic(error)
        from nico.spanish_translation_failure_diagnostic import sanitize_translation_context
        context = sanitize_translation_context(value.get('translation_context'))
        if context is not None:
            result['translation']['context'] = context
    return result


def renderer_failure_diagnostic(stage, language):
    stage = object_value(stage)
    execution = object_value(stage.get('stage_execution'))
    package = object_value(stage.get('report_package'))
    reasons = ('detached_stage_execution_failed', 'report_generation_failed',
        'generated_pdf_not_parseable', 'comprehensive_final_report_semantic_contract_failed',
        'prior_stage_results_unavailable', 'canonical_scoring_stage_unavailable',
        'canonical_scoring_assessment_unavailable', 'comprehensive_provider_registry_unavailable',
        'final_report_provider_unavailable', 'spanish_report_translation_surface_unavailable',
        'spanish_report_runtime_cache_binding_failed', 'decision_grade_report_contract_failed') + tuple('final_report_' + suffix for suffix in (
        'execution_timeout', 'publication_deadline_exceeded', 'provider_invalid_result',
        'result_identity_mismatch', 'package_missing', 'id_missing', 'markdown_missing',
        'html_missing', 'json_missing', 'markdown_hash_missing', 'markdown_hash_invalid',
        'markdown_hash_mismatch', 'html_hash_missing', 'html_hash_invalid', 'html_hash_mismatch',
        'canonical_hash_missing', 'canonical_hash_invalid', 'canonical_hash_mismatch',
        'pdf_missing', 'pdf_invalid_base64', 'pdf_invalid', 'pdf_hash_missing',
        'pdf_hash_invalid', 'pdf_hash_mismatch', 'identity_missing', 'identity_mismatch'))
    provider_class, provider_error = provider_failure_classification(stage.get('reason'))
    quality = object_value(package.get('report_quality_contract'))
    quality_keys = (
        'score_band_separated_from_assurance', 'bounded_static_scoring_discloses_assurance',
        'weighted_scoring_explicit', 'shared_control_truth_reconciled', 'executive_risk_truth_reconciled',
        'executive_risk_register_consolidated', 'executive_risks_use_stable_ids',
        'executive_risks_include_cost_and_residual', 'unverified_medium_candidates_not_p1',
        'evidence_health_summary_present', 'scope_boundaries_present', 'assumption_register_present',
        'how_to_use_present', 'express_quality_front_matter', 'pdf_page_count_label_matches_artifact',
        'semantic_html', 'markdown_evidence_appendix', 'markdown_human_review_acceptance_gate',
        'decision_grade_contract_serialized', 'backlog_export_generated', 'backlog_items_unique',
        'historical_delta_generated_only_when_comparable')
    def flag(value):
        return 'true' if value is True else 'false' if value is False else 'missing' if value is None else 'other'
    return {
        'schema': 'nico.renderer-failure-diagnostic.v1',
        'language': classification(language, ('en', 'es-MX')),
        'status': classification(stage.get('status'), ('blocked', 'failed', 'error')),
        'reason': classification(stage.get('reason'), reasons),
        'error_code': classification(stage.get('error_code'), reasons),
        'worker_failure_class': classification(stage.get('worker_failure_class'), ('process_signal', 'child_exception', 'worker_process_exit')),
        'worker_error_type': classification(stage.get('worker_error_type'), _RENDERER_EXCEPTIONS),
        'provider_failure_class': provider_class,
        'v2_publication': v2_publication_failure_diagnostic(stage.get('v2_production_authority')),
        'provider_error_type': provider_error,
        'package_present': bool(package),
        'pdf_error_present': type(package.get('pdf_error')) is str and bool(package['pdf_error']),
        'quality_present': bool(quality),
        'quality_failed_checks': [key for key in quality_keys if quality.get(key) is False],
        'quality_unclassified_count': sum(type(quality.get(key)) is not bool for key in quality_keys),
        'worker_exit_signal': classification(stage.get('worker_exit_signal'), ('SIGKILL', 'SIGTERM', 'SIGSEGV', 'SIGABRT', 'SIGBUS', 'SIGILL', 'SIGXCPU', 'SIGXFSZ')),
        'local_render_deadline_expired': flag(stage.get('local_render_deadline_expired')),
        'worker_termination_confirmed': flag(execution.get('worker_termination_confirmed')),
        'physical_worker_exit_confirmed': flag(execution.get('physical_worker_exit_confirmed')),
        'artifacts_available': flag(stage.get('artifacts_available')),
        'pdf_present': type(package.get('pdf_base64')) is str and bool(package['pdf_base64']),
    }
