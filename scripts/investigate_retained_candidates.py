"""Offline exact-commit review assistance. No network, scanner or disposition writes."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess

from nico.candidate_source_observations_v1 import observe_python_source, investigate_candidate, MAX_SOURCE_BYTES


def investigate(canonical: dict, checkout: Path) -> dict:
    identity = canonical['identity']
    sha, repository = identity['commit_sha'], identity['repository']
    import re
    if not re.fullmatch(r'[0-9a-f]{40}', sha) or not repository or not identity.get('run_id'):
        raise ValueError('exact retained run/repository/commit identity required')
    rows = canonical['assessment']['canonical_scanner_finding_register']['findings']
    if not isinstance(rows, list) or len(rows) > 10000 or any(not isinstance(row, dict) for row in rows):
        raise ValueError('bounded candidate register required')
    def git(*args):
        env = {'PATH': os.defpath, 'LANG': 'C.UTF-8', 'GIT_NO_REPLACE_OBJECTS': '1',
               'GIT_NO_LAZY_FETCH': '1', 'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0',
               'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull}
        return subprocess.run(['git', '--no-replace-objects', '-c', 'protocol.allow=never', *args],
            cwd=checkout, env=env, capture_output=True, check=True, timeout=15).stdout
    # Require the exact object locally; never fetch or infer a current branch.
    if git('rev-parse', sha + '^{commit}').decode().strip() != sha:
        raise ValueError('exact source commit unavailable')
    cache, packets, total = {}, [], 0
    for row in rows:
        path = row.get('source_path') or row.get('path') or ''
        observation = {'status': 'unavailable'}
        if (row.get('category') == 'static' and isinstance(path, str) and path.endswith('.py')
                and not path.startswith('/') and '\\' not in path
                and all(p not in {'', '..', '.'} for p in path.split('/'))
                and not any(ord(c) < 32 for c in path)):
            if path not in cache:
                listing = git('ls-tree', '-z', sha, '--', ':(literal)' + path)
                if listing.startswith((b'100644 blob ', b'100755 blob ')) and listing.count(b'\0') == 1:
                    oid = listing.split(b' ', 2)[2].split(b'\t', 1)[0].decode()
                    size = int(git('cat-file', '-s', oid))
                    if size <= MAX_SOURCE_BYTES and total + size <= 64 * 1024 * 1024:
                        data = git('cat-file', 'blob', oid)
                        total += len(data)
                        observation = observe_python_source(data, repository=repository, commit_sha=sha, path=path, blob_oid=oid)
                cache[path] = observation
            observation = cache[path]
        packets.append(investigate_candidate(row, observation, observed_commit=sha,
            expected_commit=sha, expected_repository=repository))
    return {'artifact_schema': 'nico.offline-candidate-investigation.v1',
        'identity': {k: identity[k] for k in ('run_id', 'repository', 'commit_sha')},
        'source_bytes_read': total, 'source_paths_attempted': len(cache),
        'candidate_count': len(rows), 'bounded_rule_analysis_completed': sum(p['bounded_rule_analysis_completed'] for p in packets),
        'remaining_reasons': dict(Counter(p['unresolved_questions'][0] for p in packets if not p['bounded_rule_analysis_completed'])),
        'human_review_required': True, 'client_delivery_allowed': False, 'score_effect': 'none',
        'model_invocations': 0, 'packets': packets}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--canonical', required=True, type=Path)
    parser.add_argument('--checkout', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.canonical.stat().st_size > 128 * 1024 * 1024:
        raise ValueError('canonical size limit exceeded')
    data = args.canonical.read_bytes()
    result = investigate(json.loads(data), args.checkout)
    result['input_sha256'] = hashlib.sha256(data).hexdigest()
    # Exclusive creation preserves original evidence and earlier review outputs.
    with args.output.open('x', encoding='utf-8') as target:
        json.dump(result, target, sort_keys=True)
    print(json.dumps({k: v for k, v in result.items() if k not in {'packets', 'identity'}}))


if __name__ == '__main__':
    main()
