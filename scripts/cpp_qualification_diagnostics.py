"""Bounded console diagnostics, never collection acceptance or scoring proof."""

# Exact literal codes only. A plausible prefix is not permission to log text.
_CODES = frozenset(prefix + suffix for prefix, suffixes in (
    ('qualification_', '''collection_invalid configuration_unproven failed interrupted
        collection_contract_invalid compiler_collection_contract_invalid evidence_budget
        probe_invalid probe_unproven_without_runtime_evidence runtime_evidence_missing
        artifact_invalid artifact_path_invalid artifact_existing_mismatch
        acquisition_deadline checkout_identity_mismatch manifest_invalid source_digest_mismatch'''),
    ('worker_configuration_probe_', '''failed interrupted deadline artifact_reference_invalid
        artifact_retention_failed compiler_collection_invalid compiler_evidence_invalid
        compiler_failed compiler_incomplete compiler_plan_invalid runtime_incomplete
        static_failed static_incomplete operation_failed fileapi_failed fileapi_invalid
        native_tests_failed tests_incomplete generation_budget_exhausted generation_incomplete'''),
    ('worker_project_static_stage_', '''analysis_failed analysis_incomplete artifact_reference_invalid
        artifact_retention_failed boundary_invalid cleanup_failed collection_mismatch
        compiler_collection_policy_invalid contract_invalid deadline environment_failed
        environment_flag_invalid failed fallback_failed header_evidence_incomplete image_mismatch
        interrupted operation_failed private_invalid restore_mismatch source_mismatch
        storage_invalid target_failure'''),
    ('worker_runtime_', '''artifact_unavailable deadline diagnostic_contract_invalid evidence_invalid
        execution_contract_invalid failed functional_failed functional_results_invalid fuzz_failed
        fuzz_metrics_invalid reclamation_failed sanitizer_discovery_invalid sanitizer_failed scheduling_invalid'''),
) for suffix in suffixes.split())


def _mapping(value):
    return value if type(value) is dict else {}


def _code(value):
    if value is None:
        return None
    return value if type(value) is str and len(value) <= 128 and value in _CODES else 'unrecognized_error'


def _count(value):
    # Reject booleans, coercion and unbounded integers. Unknown is never zero.
    return value if type(value) is int and 0 <= value <= 1000000 else None


def _milliseconds(value):
    return value if type(value) is int and 0 <= value <= 100000000 else None


def _boolean(value):
    return value if type(value) is bool else None


def execution_summary(value):
    """Fixed scalar observations only; never commands, output, or acceptance."""
    value = _mapping(value)
    code = value.get('exit_code')
    return {'exit_code': code if type(code) is int and -255 <= code <= 255 else None,
            'timed_out': _boolean(value.get('timed_out')),
            'output_truncated': _boolean(value.get('output_truncated')),
            'duration_ms': _milliseconds(value.get('duration_ms'))}


def _baseline_tests(probe):
    import base64
    import binascii
    from nico.assessment_cpp_full_project import _junit

    operations = probe.get('operations')
    operations = operations if type(operations) is list and len(operations) <= 10000 else []
    selected = {}
    for key in ('baseline-tests', 'baseline-test-log', 'baseline-junit'):
        rows = [row for row in operations if type(row) is dict and row.get('id') == key]
        selected[key] = {'state': 'available' if len(rows) == 1 else
                         'ambiguous' if rows else 'unavailable',
                         **execution_summary(rows[0] if len(rows) == 1 else None)}
    result = _mapping(probe.get('tests_result'))
    names = probe.get('tests_discovered')
    counts = {key: len(value) if type(value) is list and len(value) <= 10000 else None
              for key, value in [('required', names),
                  *((key, result.get(key)) for key in ('executed', 'passed', 'skipped'))]}
    junit = result.get('junit')
    state = 'unavailable'
    consistent = None
    if type(junit) is str:
        state = 'oversized'
        if len(junit) <= 4 * ((2 * 1024 * 1024 + 2) // 3):
            try:
                raw = base64.b64decode(junit, validate=True)
                if len(raw) > 2 * 1024 * 1024:
                    state = 'oversized'
                elif (type(names) is not list or not 1 <= len(names) <= 10000
                      or any(type(name) is not str or len(name) > 250 for name in names)):
                    state = 'population_unavailable'
                else:
                    executed, passed, skipped = _junit(raw, names)
                    state = 'parsed'
                    from nico.assessment_cpp_runtime_execution import _completed_sanitizer_test_failure
                    operation = selected['baseline-tests']
                    if (operation['state'] == 'available' and operation['exit_code'] is not None
                            and operation['timed_out'] is False
                            and operation['output_truncated'] is False):
                        consistent = bool((operation['exit_code'] == 0
                            and passed == sorted(names) and not skipped)
                            or _completed_sanitizer_test_failure(operation,
                                {'required': sorted(names), 'executed': executed,
                                 'passed': passed, 'skipped': skipped}, raw))
            except (binascii.Error, UnicodeEncodeError):
                state = 'invalid_encoding'
            except ValueError as exc:
                state = {'worker_full_project_xml_invalid': 'invalid_xml',
                         'worker_full_project_test_population_invalid': 'population_mismatch'}.get(
                             str(exc), 'invalid_evidence')
            except (TypeError, SyntaxError):
                state = 'invalid_xml'
    return {'operations': selected, 'counts': counts, 'junit_state': state,
            'junit_consistent_with_exit': consistent,
            'log_truncated': _boolean(result.get('log_truncated')),
            'junit_truncated': _boolean(result.get('junit_truncated')),
            'tests_passed': _boolean(probe.get('tests_passed'))}


def _sanitizer_operation(value):
    # Never infer a sanitizer kind from a generic sanitizer_failed code.
    operations = {f'runtime-{kind}-{phase}': {'kind': kind, 'phase': phase}
                  for kind in ('address', 'undefined')
                  for phase in ('configure', 'build', 'discover', 'tests', 'junit')}
    return operations.get(value) if type(value) is str else None


def failure_diagnostic(evidence, error):
    """Copy only fixed codes/counts from already retained data, without I/O.

    Static analyzed counts may include Clang fallback. These are observations
    from a rejected receipt, not verified qualification or primary-tool credit.
    Missing or invalid data stays null. Baseline JUnit is parsed with existing
    guards solely for a fixed diagnostic state; no names or raw text escape.
    Fixed keys and scalar bounds keep JSON below 4096 bytes.
    """
    probe = _mapping(_mapping(evidence).get('probe'))
    static = _mapping(probe.get('project_static'))
    fallback = _mapping(static.get('clang_fallback'))
    compiler = _mapping(probe.get('project_compiler_collection'))
    primary = _mapping(static.get('primary_diagnostics'))
    runtime = _mapping(probe.get('runtime_summary'))
    code = (error.args[0] if isinstance(error, ValueError) and len(error.args) == 1
            else 'qualification_interrupted' if isinstance(error, KeyboardInterrupt)
            else 'unrecognized_error')
    return {
        'schema': 'nico.cpp-qualification-failure-diagnostic.v1',
        'qualification_error': _code(code),
        'probe_error': _code(probe.get('error')),
        'independent_collection_error': _code(probe.get('independent_collection_error')),
        'static_stage_error': _code(_mapping(probe.get('project_static_stage')).get('error')),
        'runtime_error': _code(_mapping(probe.get('runtime_evidence')).get('error')),
        'baseline_tests': _baseline_tests(probe),
        'sanitizer_failure': {
            key: _sanitizer_operation(runtime.get(key))
            for key in ('first_failure_operation', 'failure_operation')},
        'primary_diagnostics': {
            **{key: _milliseconds(primary.get(key)) for key in
               ('wall_duration_ms', 'execution_duration_ms', 'max_execution_duration_ms')},
            **{key: _count(primary.get(key)) for key in
               ('executions', 'analyzed', 'missing_execution', 'timed_out',
                'nonzero_exit', 'output_truncated', 'record_error', 'syntax_error', 'internal_ast_error')},
        },
        'retained_counts': {
            'static': {key: _count(static.get(key + '_contexts_count'))
                       for key in ('required', 'attempted', 'analyzed')},
            'clang_fallback': {key: _count(len(fallback[key + '_contexts']))
                               if type(fallback.get(key + '_contexts')) is list else None
                               for key in ('required', 'attempted', 'analyzed')},
            'headers': {'population': _count(static.get('header_population_count')),
                        'unvisited': _count(static.get('header_unvisited_files_count'))},
            'compiler_collection': {key: _count(compiler.get(key + '_contexts_count'))
                                    for key in ('required', 'attempted', 'completed', 'failed', 'unparsed')},
        },
    }
