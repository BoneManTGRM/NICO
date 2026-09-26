"""Additive acceptance for fully collected runtime evidence, not target success.

The original runtime validator and its failure result remain authoritative.
This narrower decision permits a completed sanitizer finding only after every
independent check finished and the failed test's diagnostic was retained. It
does not qualify an image, activate production, or classify exploitability.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib

from nico.assessment_cpp_full_project import _json
from nico.assessment_cpp_runtime_execution import _ok
from nico.assessment_cpp_runtime_scope import validate_retained_runtime
from nico.assessment_worker_receipts import canonical_bytes


def _sha(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def validate_runtime_collection(raw, targets, project_options, scope):
    """Reconstruct a source-bound collection decision without changing evidence.

    A rejected decision raises. A returned decision always retains the original
    summary, including any failed target tests and its ``complete=False``.
    """
    reconstructed = validate_retained_runtime(raw, targets, project_options, scope)
    retained = _json(raw)
    evidence, plan, summary = retained['evidence'], reconstructed['plan'], reconstructed['summary']
    error = 'worker_runtime_collection_incomplete'

    def require(condition):
        if not condition:
            raise ValueError(error)

    # Older schemas retain their original interpretation and cannot acquire a
    # completed-failure classification without v4's exact Failed-test proof.
    require(evidence.get('schema') == 'nico.cpp-runtime-evidence.v4')
    require(plan['sanitizers']['kinds'] == ['address', 'undefined'])
    require(all(type(plan['fuzz'][key]) is int and plan['fuzz'][key] > 0
                for key in ('replay_runs', 'campaign_runs')))
    require(summary.get('failure_operation') is None)
    require(evidence['error'] in (None, 'worker_runtime_sanitizer_failed'))

    functional = evidence['functional']
    require(all(_ok(functional[key]) for key in ('setup', 'operation', 'results_read')))
    require(summary['functional']['executed'] == plan['functional']['selected_tests']
            and summary['functional']['passed'] == plan['functional']['selected_tests']
            and not summary['functional']['failed'] and not summary['functional']['skipped'])

    failed_kinds = []
    for row, result in zip(evidence['sanitizers'], summary['sanitizers']):
        require(all(_ok(row[key]) for key in ('configure', 'build', 'discovery', 'junit_read')))
        require(result['required'] and result['executed'] == result['required'] and not result['skipped'])
        if not _ok(row['tests']):
            # validate_retained_runtime already verified every Failed JUnit
            # entry, exact invocation, full population, exit=8 and no timeout.
            require(result.get('state') == 'failed' and result['passed'] != result['required'])
            failed_kinds.append(row['kind'])
        else:
            require(result['passed'] == result['required'])

    require([row['kind'] for row in summary['failure_diagnostics']] == failed_kinds)
    for diagnostic, parsed in zip(evidence['failure_diagnostics'], summary['failure_diagnostics']):
        require(_ok(diagnostic['log_read']) and _ok(diagnostic['resources']))
        log, resources = parsed['log'], parsed['resources']
        require(log['state'] == 'captured' and log.get('truncated') is False and log.get('bytes', 0) > 0)
        require(isinstance(resources, dict))
        events = resources['memory_events']
        require(isinstance(events, dict) and all(type(events.get(key)) is int and events[key] == 0
            for key in ('oom', 'oom_kill', 'oom_group_kill')))
        require(type(resources['memory_current_bytes']) is int
                and type(resources['memory_peak_bytes']) is int and resources['memory_peak_bytes'] > 0)
        require(type(resources['scratch_capacity_bytes']) is int and resources['scratch_capacity_bytes'] > 0
                and type(resources['scratch_available_bytes']) is int and resources['scratch_available_bytes'] > 0)

    fuzz = evidence['fuzz']
    require(all(_ok(fuzz[key]) for key in ('corpus_stage', 'configure', 'build', 'campaign')))
    require(len(fuzz['replays']) == len(plan['fuzz']['corpus']) and all(_ok(row) for row in fuzz['replays']))
    metrics = summary['fuzz']
    require(metrics['campaign_completed'] is True
            and type(metrics['campaign_executions']) is int
            and metrics['campaign_executions'] >= plan['fuzz']['campaign_runs']
            and type(metrics['campaign_coverage_signal']) is int and metrics['campaign_coverage_signal'] > 0)
    require(all(_ok(row) for row in evidence['reclamations']))
    require(summary['complete'] is (not failed_kinds))
    require(evidence['error'] == ('worker_runtime_sanitizer_failed' if failed_kinds else None))

    return {
        'schema': 'nico.cpp-runtime-collection.v1',
        'status': 'complete_with_findings' if failed_kinds else 'passed',
        'collection_complete': True,
        'target_tests_passed': summary['complete'],
        'full_project_qualified': False,
        'production_qualified': False,
        'source_population_sha256': _sha(targets),
        'project_options_sha256': _sha(project_options),
        'runtime_scope_sha256': _sha(scope),
        'runtime_plan_sha256': _sha(plan),
        'runtime_artifact_sha256': hashlib.sha256(raw).hexdigest(),
        'runtime_native_evidence_sha256': summary['native_evidence_sha256'],
        'runtime_summary_sha256': _sha(summary),
        'summary': deepcopy(summary),
    }
