"""Prepare offline evidence requests from retained triage; never disposition candidates.

Reads the existing validated compact triage format. Grouping identical requests
within one repository/commit is preparation only, not shared proof or approval.
No network, source execution, database access or assessment mutation occurs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import re

from nico.candidate_technical_triage_v1 import load_default_technical_triage


def prepare(path: Path | None = None) -> dict:
    payload = load_default_technical_triage(path)
    repository, commit = payload.get('r'), payload.get('c')
    if (not isinstance(repository, str) or not repository.strip()
            or not isinstance(commit, str) or not re.fullmatch('[0-9a-f]{40}', commit)):
        raise ValueError('retained_triage_scope_invalid')
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    requests, next_steps = defaultdict(list), defaultdict(list)
    reasons, verdicts = Counter(), Counter()
    candidates, unknown = [], []
    with_gaps = 0
    for candidate_id, code, _rank in payload['x']:
        # The shared loader validates trimmed strings. This packet must preserve
        # exact identifiers and must not leak a raw code through a KeyError.
        if any(not isinstance(value, str) or not value or value != value.strip()
               for value in (candidate_id, code)):
            raise ValueError('retained_triage_identifier_invalid')
        entry = payload['q'][code]
        verdict, proposal, next_step, gaps = entry[0], entry[2], entry[6], entry[7]
        if not isinstance(gaps, list) or any(not isinstance(gap, str) or not gap.strip() for gap in gaps):
            raise ValueError('retained_triage_proof_gaps_invalid')
        if not isinstance(next_step, str):
            raise ValueError('retained_triage_next_step_invalid')
        verdicts[verdict] += 1
        with_gaps += bool(gaps)
        candidates.append({'candidate_id': candidate_id, 'retained_verdict': verdict,
                           'retained_proposal': proposal, 'rationale_code': code})
        if verdict != 'needs_review':
            continue
        reasons[code] += 1
        if not gaps:
            unknown.append(candidate_id)
        for gap in sorted(set(gaps)):
            requests[gap].append(candidate_id)
        next_steps[(code, next_step)].append(candidate_id)
    return {
        'artifact_schema': 'nico.retained-triage-evidence-requests.v1',
        'scope': {'repository': repository, 'commit_sha': commit},
        'retained_payload_sha256': digest,
        'scope_limit': 'Historical retained triage only; no current-run or deployed-artifact coverage established.',
        'candidate_count': len(candidates), 'candidate_references': candidates,
        'verdict_counts': dict(verdicts), 'unresolved_reason_counts': dict(reasons),
        'coverage': {'candidates_with_recorded_proof_gaps': with_gaps,
                     'candidates_without_recorded_proof_gaps': len(candidates) - with_gaps,
                     'meaning': 'Recorded gaps only; an empty gap list is not proof of completeness or safety.'},
        'evidence_requests': [{'retained_proof_gap': gap, 'candidate_ids': sorted(ids)}
                              for gap, ids in sorted(requests.items())],
        'next_step_groups': [{'rationale_code': code, 'retained_next_step': step,
                             'candidate_ids': sorted(ids)}
                            for (code, step), ids in sorted(next_steps.items())],
        'unresolved_without_recorded_gaps': sorted(unknown),
        'grouping_limit': 'Identical requests do not establish shared applicability; verify evidence against each original candidate.',
        'runtime_validation_performed': False, 'human_approval_status': 'pending',
        'human_review_required': True, 'client_delivery_allowed': False,
        'score_effect': 'none', 'reviewer_time_saved_seconds': None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--triage', type=Path, help='Optional authorized compact triage file; defaults to repository-retained evidence.')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.triage)
    # Retained text may be sensitive. Create privately without changing any
    # existing file's permissions; O_EXCL also rejects an existing symlink.
    with open(args.output, 'x', encoding='utf-8',
              opener=lambda path, flags: os.open(path, flags, 0o600)) as target:
        json.dump(result, target, indent=2, sort_keys=True)
        target.write('\n')
    print(json.dumps({'candidate_count': result['candidate_count'],
                      'unresolved_candidate_count': sum(result['unresolved_reason_counts'].values()),
                      'evidence_request_count': len(result['evidence_requests']),
                      'next_step_group_count': len(result['next_step_groups'])}))


if __name__ == '__main__':
    main()
