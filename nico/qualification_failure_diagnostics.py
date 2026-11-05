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
