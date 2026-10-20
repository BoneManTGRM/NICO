"""Scoped histogram conformance, excluded from maturity and quality judgments."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any
import re

from nico.full_assessment_complexity_evidence import _is_source_path
from nico.source_function_measurement_report_v1 import _bound
from nico.source_function_measurements_v1 import _integer, _json, _path

VERSION = 'nico.source-function-conformance.v1'
KEY = 'source_function_conformance_v1'
SUPPORTED = ('.py', '.js', '.jsx', '.ts', '.tsx')
LIMITATIONS = (
    'Function complexity conformance measures CC<=20 in enumerated functions only; excluded from overall maturity. '
    'It does not establish architecture quality or delivery velocity. Languages use different counting rules; combined totals are descriptive. '
    'Nesting<=4 is a separate marginal measure; joint CC/nesting conformance cannot be inferred. '
    'Helper extraction and trivial-function dilution can increase the percentage without reducing decision burden; never infer improvement from the ratio alone. '
    'Absolute violations and sum(CC-1) remain visible. Module/class initializer residuals and whole-source decision burden are unavailable; Python lambdas are not enumerated. '
    'Existing source exclusions remain outside the population; unsupported C++ receives no credit. '
    'Qualification requires a complete acquired eligible inventory; ambiguous content-based exclusions remain unavailable. '
    'Text hashes bind decoded supplied source, not original repository bytes; authenticity relies on trusted server persistence, not cryptographic attestation or independently enforced completed-stage immutability.'
)


def _paths(value: Any) -> set[str]:
    if not isinstance(value, list) or any(not isinstance(p, str) or not p for p in value) or len(set(value)) != len(value):
        raise ValueError('invalid coverage paths')
    return set(value)


def _qualified_coverage(repository: dict, complexity: dict, value: dict) -> dict:
    coverage = complexity.get('profile_coverage')
    independent = repository.get('file_evidence', {}).get('profile_coverage')
    if not isinstance(coverage, dict) or _json(coverage) != _json(independent):
        raise ValueError('coverage binding mismatch')
    if coverage.get('version') != 'nico.repository_profile_coverage.v1' or coverage.get('inventory_complete') is not True or coverage.get('coverage_denominator_scope') != 'complete_source_inventory':
        raise ValueError('complete source inventory required')
    files = value['files']
    paths = {row['path'] for row in files}
    supported = {row['path'] for row in files if row['path'].lower().endswith(SUPPORTED)}
    observation = repository['architecture_evidence']['source_observation']
    observed = {row['path'] for row in observation['input_inventory']}
    sampled = _paths(coverage.get('sampled_paths'))
    analyzed = _paths(coverage.get('analyzed_source_paths'))
    if sampled != observed or not paths <= sampled or not supported <= analyzed or not analyzed <= paths:
        raise ValueError('coverage membership mismatch')
    _external_coverage(coverage)
    _coverage_counts(coverage, paths, sampled, analyzed)
    _parser_population(coverage, files, supported)
    return deepcopy(coverage)


def _external_coverage(coverage: dict) -> None:
    if coverage.get('inventory_scope') != 'parent_repository_tree' or coverage.get('submodule_contents_acquired') is not False:
        raise ValueError('external acquisition scope required')
    for key, fields in (('submodule_entries', {'path', 'commit_sha'}),
                        ('lfs_pointer_entries', {'path', 'oid', 'size_bytes'})):
        entries = coverage.get(key)
        if not isinstance(entries, list):
            raise ValueError('explicit external inventory required')
        seen = set()
        for row in entries:
            if not isinstance(row, dict) or set(row) != fields:
                raise ValueError('invalid external inventory entry')
            path = _path(row['path'])
            if path in seen:
                raise ValueError('duplicate external inventory entry')
            seen.add(path)
            if key == 'submodule_entries':
                digest, pattern = row['commit_sha'], r'[0-9a-f]{40}'
            else:
                _integer(row['size_bytes'])
                digest, pattern = row['oid'], r'sha256:[0-9a-f]{64}'
            if not isinstance(digest, str) or not re.fullmatch(pattern, digest):
                raise ValueError('invalid external object identity')


def _coverage_counts(coverage: dict, paths: set[str], sampled: set[str], analyzed: set[str]) -> None:
    for key, expected in (('eligible_source_files',len(paths)), ('sampled_eligible_source_files',len(paths)),
                          ('unsampled_eligible_source_files',0), ('analyzed_source_files',len(analyzed)),
                          ('profiled_text_files',len(sampled))):
        if _integer(coverage.get(key)) != expected:
            raise ValueError('incomplete acquisition or contradictory coverage')
    excluded = _paths(coverage.get('complexity_excluded_paths'))
    if excluded & paths or any(_is_source_path(p) for p in excluded):
        raise ValueError('invalid excluded membership')
    if _integer(coverage.get('complexity_excluded_source_files')) != len(excluded) or _integer(coverage.get('observed_source_files')) != len(paths) + len(excluded):
        raise ValueError('source population mismatch')
    if _paths(coverage.get('sampled_unanalyzed_source_paths')) != paths - analyzed:
        raise ValueError('unanalyzed population mismatch')


def _parser_population(coverage: dict, files: list[dict], supported: set[str]) -> None:
    for key in ('unavailable_paths', 'size_excluded_paths', 'symlink_paths_not_followed'):
        if any(_is_source_path(p) and p.lower().endswith(SUPPORTED) for p in _paths(coverage.get(key))):
            raise ValueError('eligible source acquisition incomplete')
    if any(row['path'] in supported for row in coverage['lfs_pointer_entries']):
        raise ValueError('eligible source is an unacquired LFS object')
    for row in files:
        if row['path'] in supported:
            method = 'python_ast' if row['path'].lower().endswith('.py') else 'typescript_compiler_ast'
            if row['status'] != 'measured' or row['method'] != method:
                raise ValueError('complete measured parser population required')
        elif row.get('metrics') is not None:
            raise ValueError('unsupported language cannot receive conformance credit')


def _population(files: list[dict]) -> dict:
    count = sum(row['metrics']['function_count'] for row in files)
    result = {'files': len(files), 'function_count': count}
    for dimension, threshold in (('cc',20), ('nesting',4)):
        histogram = Counter()
        for row in files:
            histogram.update(row['metrics'][dimension]['histogram'])
        measured = sum(histogram.values())
        conforming = sum(n for k,n in histogram.items() if int(k) <= threshold)
        result[dimension] = {'threshold': threshold, 'conforming': conforming,
            'violations': measured-conforming, 'measured_functions': measured,
            'percentage': round(100*conforming/measured,2) if measured else None,
            'maximum': max(map(int,histogram),default=None)}
        if dimension == 'cc':
            result[dimension]['sum_cc_minus_1'] = sum((int(k)-1)*n for k,n in histogram.items())
        else:
            result[dimension]['missing_functions'] = count-measured
            # A partial nesting marginal cannot represent all enumerated functions.
            if measured != count:
                result[dimension]['percentage'] = None
    return result


def build_conformance(context: dict, repository: dict, complexity: dict, *, witness=None) -> dict:
    """Pure projection: never mutate source evidence or legacy scoring inputs."""
    result = {'version': VERSION, 'status': 'unavailable', 'identity': None,
              'included_in_overall_maturity': False, 'architecture_quality_established': False,
              'delivery_velocity_established': False, 'languages': [], 'combined': None,
              'coverage': None, 'exclusions': {}, 'limitations': LIMITATIONS}
    try:
        from nico.source_function_witness_v1 import valid_witness
        if not valid_witness(witness, context, repository, complexity):
            raise ValueError('independent persisted collection witness required')
        value = _bound(context, repository, complexity)
        if value is None:
            raise ValueError('measurements absent, invalid or independently unbound')
        coverage = _qualified_coverage(repository, complexity, value)
    except (ValueError, TypeError, KeyError, AttributeError):
        result['reason'] = 'A verified collection contract from trusted server persistence, complete bound acquisition and measured function histograms are required.'
        return result
    files = [row for row in value['files'] if row['path'].lower().endswith(SUPPORTED)]
    combined = _population(files)
    result.update(status='qualified' if combined['function_count'] else 'not_applicable',
                  identity=deepcopy(value['identity']), coverage=coverage, combined=combined,
                  inventory_sha256=value['inventory_sha256'],
                  producer_source_sha256=deepcopy(value['producer_source_sha256']))
    result['languages'] = [{'language':language, **_population([row for row in files if row['language']==language])}
                           for language in sorted({row['language'] for row in files})]
    result['exclusions'] = {
        'source_policy_paths': coverage['complexity_excluded_paths'],
        'unsupported_observed_paths': [row['path'] for row in value['files'] if not row['path'].lower().endswith(SUPPORTED)],
        'submodule_entries': deepcopy(coverage['submodule_entries']),
        'submodule_contents_acquired': False,
    }
    return result
