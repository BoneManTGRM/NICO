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


def failure_diagnostic(evidence, error):
    """Copy only fixed codes/counts from already retained data, without I/O.

    Static analyzed counts may include Clang fallback. These are observations
    from a rejected receipt, not verified qualification or primary-tool credit.
    Missing or invalid data stays null. No source, operation, path or raw error
    text is traversed. Fixed keys and scalar bounds keep JSON below 4096 bytes.
    """
    probe = _mapping(_mapping(evidence).get('probe'))
    static = _mapping(probe.get('project_static'))
    fallback = _mapping(static.get('clang_fallback'))
    compiler = _mapping(probe.get('project_compiler_collection'))
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
