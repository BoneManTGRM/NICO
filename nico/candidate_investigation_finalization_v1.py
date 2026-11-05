"""Invocation-local final candidate analysis, using only retained bound observations."""
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar

from nico.candidate_investigation_pipeline_v1 import (
    display_investigation, fingerprint, investigate_register, scope_of,
)
from nico.candidate_source_observations_v1 import candidate_source_path

_ACTIVE = ContextVar('candidate_investigation_finalization', default=None)
FINAL_KEY = 'final_candidate_investigation'


def _analysis_identity(row):
    if not isinstance(row, Mapping):
        return None
    # These fields identify the exact scanner claim and source analyzed. Human
    # routing/enrichment is not evidence of a new analysis or a disposition.
    fields = ('candidate_id', 'finding_id', 'raw_fingerprint', 'scanner', 'tool', 'category',
              'rule_id', 'rule', 'line', 'column', 'exact_commit_sha', 'source_commit_sha',
              'source_repository', 'evidence_quality', 'evidence', 'occurrence_count')
    result = {key: row.get(key) for key in fields}
    raw = row.get('source_path') or row.get('path')
    normalized = candidate_source_path(raw)
    result['source_path'] = normalized if normalized is not None else raw
    if 'path' in row:
        path = row.get('path')
        normalized_path = candidate_source_path(path)
        result['path'] = normalized_path if normalized_path is not None else path
    return result


@contextmanager
def final_investigation_scope(context):
    """Only the real publication caller provides the original durable stage input."""
    scope = scope_of(context)
    stages = context.get('prior_stage_results')
    stages = stages if isinstance(stages, Mapping) else {}
    repository = stages.get('repository_and_delivery_evidence') or {}
    repository = repository.get('repository_evidence') if isinstance(repository, Mapping) else None
    capture = repository.get('candidate_source_observations') if isinstance(repository, Mapping) else None
    scoring = stages.get('evidence_reconciliation_and_scoring') or {}
    if isinstance(scoring, Mapping) and 'candidate_source_observations' in scoring:
        capture = scoring['candidate_source_observations']
    assessment = scoring.get('assessment') if isinstance(scoring, Mapping) else None
    original = assessment.get('canonical_scanner_finding_register') if isinstance(assessment, Mapping) else None
    state = {'scope': scope, 'capture': capture, 'original': original, 'result': None, 'input': None}
    token = _ACTIVE.set(state)
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def finalize_investigation(canonical):
    state = _ACTIVE.get()
    if state is None:
        return canonical  # Localized reads and exports must never launch analyses.
    assessment = canonical.get('assessment')
    register = assessment.get('canonical_scanner_finding_register') if isinstance(assessment, Mapping) else None
    if not isinstance(register, Mapping):
        return canonical
    original, scope, capture = state['original'], state['scope'], state['capture']
    reason = None
    rows = register.get('findings')
    original_view = {k: v for k, v in original.items() if k != FINAL_KEY} if isinstance(original, Mapping) else {}
    if not all(scope.values()) or not display_investigation(original_view, scope)['available']:
        reason = 'original_investigation_missing_or_stale'
    elif not isinstance(capture, Mapping) or capture.get('scope') != scope:
        reason = 'retained_capture_missing_or_stale'
    elif not isinstance(rows, list) or len(rows) != len(original.get('findings', [])):
        reason = 'candidate_population_changed'
    elif any(fingerprint(_analysis_identity(a)) != fingerprint(_analysis_identity(b)) for a, b in zip(original['findings'], rows)):
        reason = 'candidate_analysis_identity_changed'
    elif not isinstance(canonical.get('identity'), Mapping) or any(canonical['identity'].get(k) != scope[k] for k in ('run_id', 'repository', 'commit_sha')):
        reason = 'final_report_source_identity_changed'
    if reason:
        final = {'status': 'unavailable', 'reason': reason, 'human_review_required': True, 'client_delivery_allowed': False}
    else:
        digest = fingerprint(rows)
        if state['result'] is None:
            state['result'] = investigate_register(register, capture, scope)
            state['input'] = digest
        final = state['result'] if state['input'] == digest else {
            'status': 'unavailable', 'reason': 'final_candidate_input_changed',
            'human_review_required': True, 'client_delivery_allowed': False}
    # The original packet/input fingerprints remain byte-for-byte unchanged.
    return {**canonical, 'assessment': {**assessment,
        'canonical_scanner_finding_register': {**register, FINAL_KEY: final}}}
