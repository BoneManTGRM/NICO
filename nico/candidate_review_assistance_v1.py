"""Read-only reviewer packets from retained analysis, never human dispositions.

This module neither fetches source nor invokes a model. A source link is a locator,
not proof that the source has been read. Similar review profiles are not duplicates.
"""
from collections import Counter
from collections.abc import Mapping, Sequence
import hashlib
import json
import re
from urllib.parse import quote

from nico.candidate_technical_triage_v1 import ALGORITHM_VERSION

VERSION = 'nico.candidate-review-assistance.v1'


def _text(value):
    return value.strip() if isinstance(value, str) else ''


def _source_link(row, scope):
    sha = _text(row.get('source_commit_sha'))
    repository = _text(scope.get('repository'))
    path = _text(row.get('source_path') or row.get('path'))
    if not re.fullmatch(r'[0-9a-f]{40}', sha) or sha != scope.get('commit_sha'):
        return None
    if row.get('source_repository') not in (None, '', repository):
        return None
    if row.get('source_provider') != 'github':
        return None
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        return None
    if (not path or path.startswith('/') or '\\' in path or ':' in path
            or any(part in {'', '.', '..'} for part in path.split('/'))
            or any(ord(c) < 32 or ord(c) == 127 for c in path)):
        return None
    line = row.get('line') or row.get('source_line')
    anchor = f'#L{line}' if type(line) is int and line > 0 else ''
    return f'https://github.com/{repository}/blob/{sha}/{quote(path, safe="/")}{anchor}'


def build_review_assistance(rows: Sequence[Mapping], scope: Mapping) -> dict:
    """Prioritize every pending record, preserving duplicates and uncertainty.

    Recommendations reuse only current deterministic evidence. No model result can
    clear a candidate here. Raw evidence and free-form rationale remain in the
    existing protected candidate view rather than being copied into this summary.
    """
    ids = Counter(_text(row.get('candidate_id')) for row in rows)
    queue = []
    completed = 0
    for index, row in enumerate(rows):
        if row.get('human_disposition_state') == 'completed':
            completed += 1
            continue
        candidate_id = _text(row.get('candidate_id'))
        limitations = []
        if not _text(scope.get('run_id')):
            limitations.append('run_scope_unverified')
        if not candidate_id or ids[candidate_id] != 1:
            limitations.append('duplicate_candidate_identity')
        source_url = _source_link(row, scope)
        if source_url is None:
            limitations.append('source_identity_or_location_unverified')
        if row.get('evidence_quality') != 'exact_source':
            limitations.append('exact_source_evidence_missing')
        if row.get('candidate_evidence_context_status') == 'ambiguous':
            limitations.append('ambiguous_context')
        if (row.get('evidence_changed') or row.get('lineage_status') == 'carried_forward_evidence_changed'
                or row.get('evidence_change_state') in {'changed', 'materially_changed', 'significant_change'}):
            limitations.append('evidence_changed')
        if (row.get('technical_triage_source_type') != 'deterministic_contextual_analysis'
                or row.get('technical_triage_model_or_version') != ALGORITHM_VERSION):
            limitations.append('analysis_not_current_deterministic')
        if row.get('technical_triage_status') != 'fresh_proposal':
            limitations.append('analysis_unavailable')
        evidence = row.get('evidence_used')
        if (not isinstance(evidence, list) or not evidence
                or not all(isinstance(item, str) and item.strip() for item in evidence)):
            limitations.append('supporting_evidence_missing')
        gaps = row.get('technical_triage_proof_gaps', row.get('proof_gaps', []))
        if not isinstance(gaps, list) or gaps:
            limitations.append('unresolved_proof_gaps')
        if (row.get('counterevidence') or row.get('conflicting_evidence')
                or row.get('counterevidence_conflict')):
            limitations.append('counterevidence_requires_review')
        severity = _text(row.get('severity')).lower()
        high_impact = severity in {'critical', 'high', 'material'} or row.get('category') in {'secret', 'secrets'}
        high_impact = high_impact or row.get('review_routing_class') == 'CRITICAL_ATTENTION'
        if row.get('individual_attention_required') or row.get('review_requires_individual_attention'):
            limitations.append('existing_individual_review_required')
        if high_impact:
            limitations.append('high_impact_individual_review')
        verdict = row.get('technical_triage_verdict')
        confidence = row.get('technical_triage_confidence')
        if not (confidence == 'high' or (type(confidence) in {int, float} and 0.85 <= confidence <= 1)):
            limitations.append('confidence_insufficient_for_nonblocking_proposal')
        recommendation = 'resolve_evidence_gaps'
        if high_impact or verdict == 'confirmed':
            recommendation = 'individual_material_review'
        elif verdict == 'not_actionable' and not limitations:
            recommendation = 'review_nonblocking_proposal'
        # Hash binds all retained inputs, including contradictions, without copying
        # any scanner payload or secret-bearing narrative into this projection.
        digest = hashlib.sha256(json.dumps({'scope': dict(scope), 'candidate': dict(row)},
            sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()
        queue.append({
            'candidate_id': candidate_id, 'record_index': index,
            'recommendation': recommendation, 'limitations': limitations,
            'source_url': source_url, 'input_sha256': digest,
            'existing_review_profile_cluster_id': _text(row.get('cluster_id')),
            'priority': 0 if high_impact or verdict == 'confirmed' else 1 if limitations else 2,
        })
    queue.sort(key=lambda item: (item['priority'], item['candidate_id'], item['record_index']))
    return {
        'artifact_schema': VERSION, 'analysis_actor': 'deterministic_retained_evidence_assistant',
        'candidate_record_count': len(rows), 'human_disposition_completed_count': completed,
        'pending_record_count': len(queue), 'queue': queue,
        'new_source_investigations_performed': 0, 'model_invocations': 0,
        'grouping_is_disposition_equivalence': False,
        'human_review_required': True, 'client_delivery_allowed': False, 'score_effect': 'none',
    }
