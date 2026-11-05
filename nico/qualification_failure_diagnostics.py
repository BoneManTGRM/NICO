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
        'runtime_complete': object_value(probe.get('runtime_summary')).get('complete') is True,
    }


def renderer_failure_diagnostic(stage, language):
    stage = object_value(stage)
    execution = object_value(stage.get('stage_execution'))
    package = object_value(stage.get('report_package'))
    reasons = ('detached_stage_execution_failed', 'report_generation_failed',
        'generated_pdf_not_parseable', 'comprehensive_final_report_semantic_contract_failed',
        'prior_stage_results_unavailable', 'canonical_scoring_stage_unavailable',
        'canonical_scoring_assessment_unavailable', 'comprehensive_provider_registry_unavailable',
        'final_report_provider_unavailable', 'spanish_report_translation_surface_unavailable',
        'spanish_report_runtime_cache_binding_failed') + tuple('final_report_' + suffix for suffix in (
        'execution_timeout', 'publication_deadline_exceeded', 'provider_invalid_result',
        'result_identity_mismatch', 'package_missing', 'id_missing', 'markdown_missing',
        'html_missing', 'json_missing', 'markdown_hash_missing', 'markdown_hash_invalid',
        'markdown_hash_mismatch', 'html_hash_missing', 'html_hash_invalid', 'html_hash_mismatch',
        'canonical_hash_missing', 'canonical_hash_invalid', 'canonical_hash_mismatch',
        'pdf_missing', 'pdf_invalid_base64', 'pdf_invalid', 'pdf_hash_missing',
        'pdf_hash_invalid', 'pdf_hash_mismatch', 'identity_missing', 'identity_mismatch'))
    def flag(value):
        return 'true' if value is True else 'false' if value is False else 'missing' if value is None else 'other'
    return {
        'schema': 'nico.renderer-failure-diagnostic.v1',
        'language': classification(language, ('en', 'es-MX')),
        'status': classification(stage.get('status'), ('blocked', 'failed', 'error')),
        'reason': classification(stage.get('reason'), reasons),
        'error_code': classification(stage.get('error_code'), reasons),
        'worker_failure_class': classification(stage.get('worker_failure_class'), ('process_signal', 'child_exception', 'worker_process_exit')),
        'worker_error_type': classification(stage.get('worker_error_type'), (
            'LayoutError', 'KeyError', 'ValueError', 'TypeError', 'MemoryError', 'TimeoutError',
            'RuntimeError', 'WorkerProcessExit', 'WorkerPayloadError', 'ImportError',
            'ModuleNotFoundError', 'UnicodeEncodeError', 'UnicodeDecodeError', 'OSError',
            'PermissionError', 'FileNotFoundError', 'RecursionError', 'AttributeError')),
        'worker_exit_signal': classification(stage.get('worker_exit_signal'), ('SIGKILL', 'SIGTERM', 'SIGSEGV', 'SIGABRT', 'SIGBUS', 'SIGILL', 'SIGXCPU', 'SIGXFSZ')),
        'local_render_deadline_expired': flag(stage.get('local_render_deadline_expired')),
        'worker_termination_confirmed': flag(execution.get('worker_termination_confirmed')),
        'physical_worker_exit_confirmed': flag(execution.get('physical_worker_exit_confirmed')),
        'artifacts_available': flag(stage.get('artifacts_available')),
        'pdf_present': type(package.get('pdf_base64')) is str and bool(package['pdf_base64']),
    }
