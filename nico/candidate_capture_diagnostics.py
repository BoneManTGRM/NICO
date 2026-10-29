"""Count-only projection of stored capture evidence; no acquisition or mutation."""
from collections import Counter
from collections.abc import Mapping

_SCOPE = ('run_id', 'repository', 'commit_sha', 'customer_id', 'project_id')
_STATUSES = frozenset({'parsed', 'source_size_limit', 'source_binding_invalid', 'source_parse_unavailable'})
_REASONS = frozenset({'source_scope_missing', 'unsupported_source', 'source_time_budget',
                     'source_size_budget', 'source_analysis_failed', 'observation_size_budget',
                     'candidate_inventory_limit', 'source_missing_or_unsupported'})


def capture_diagnostics(record: Mapping) -> dict:
    result = {'artifact_schema': 'nico.candidate-source-capture-diagnostics.v1',
              'capture_present': False, 'status': 'missing', 'scope_match': None,
              'observation_count': None, 'observation_status_counts': {}, 'budget_reason_counts': {}}
    current = record
    for key in ('stage_results', 'repository_and_delivery_evidence', 'repository_evidence'):
        current = current.get(key) if isinstance(current, Mapping) else None
    stages = record.get('stage_results')
    scoring = stages.get('evidence_reconciliation_and_scoring') if isinstance(stages, Mapping) else None
    if isinstance(scoring, Mapping) and 'candidate_source_observations' in scoring:
        current = scoring
    if not isinstance(current, Mapping) or 'candidate_source_observations' not in current:
        return result
    capture = current['candidate_source_observations']
    result.update(capture_present=True, status='malformed')
    if not isinstance(capture, Mapping) or capture.get('artifact_schema') != 'nico.persisted-candidate-investigation.v1':
        return result
    identity, scope = record.get('identity'), capture.get('scope')
    if not isinstance(identity, Mapping) or not isinstance(scope, Mapping):
        return result
    matches = all(isinstance(identity.get(k), str) and bool(identity[k]) and scope.get(k) == identity[k] for k in _SCOPE)
    result['scope_match'] = matches
    if not matches:
        result['status'] = 'scope_mismatch'
        return result
    observations, reasons = capture.get('observations'), capture.get('unavailable_reasons')
    if not isinstance(observations, Mapping) or len(observations) > 10000 or not isinstance(reasons, Mapping):
        return result
    counts = Counter()
    for observation in observations.values():
        status = observation.get('status') if isinstance(observation, Mapping) else None
        if not isinstance(status, str) or status not in _STATUSES:
            return result
        counts[status] += 1
    safe_reasons = {}
    for key in _REASONS:
        if key in reasons:
            value = reasons[key]
            if type(value) is not int or not 0 <= value <= 1000000:
                return result
            safe_reasons[key] = value
    result.update(status='available', observation_count=len(observations),
                  observation_status_counts=dict(counts), budget_reason_counts=safe_reasons)
    return result
