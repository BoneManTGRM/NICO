"""Real isolated analyzer smoke control, not the full C/C++ qualification.

Owned clean/known-diagnostic sources exercise the actual materializer, executor
and canonical receipt validator. No target repository build or human decision.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time

from nico.assessment_worker_container import run_isolated_cppcheck
from nico.assessment_worker_jobs import JobIdentity, _digest
from nico.assessment_worker_receipts import CONFIGURATION, canonical_bytes, validate_receipt
from nico.repository_snapshot import _git_environment
from nico.snapshot_repository_evidence import materialize_exact_git_inputs

SOURCES = {
    'clean.cpp': b'int add(int a, int b) { return a + b; }\n',
    'diagnostic.cpp': b'int dereference_null() { int* p = nullptr; return *p; }\n',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', type=Path, default=Path('cppcheck-worker-control.json'))
    args = parser.parse_args()
    source_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    evidence = {'schema': 'nico.cppcheck_worker_control.v1', 'status': 'UNPROVEN',
        'source_sha': source_sha, 'tool_source': 'cppcheck-opensource/cppcheck',
        'tool_revision': 'ac9db3069b9f90e81e126a090b99ad456e122cf8',
        'scope': 'owned two-translation-unit analyzer smoke control; not full qualification',
        'production_dispatch_exercised': False, 'compilation_database_verified': False,
        'header_context_verified': False, 'build_runtime_executed': False,
        'human_approval': False, 'bitcoin_executed': False}
    start = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='nico-native-control-') as temp:
            root = Path(temp)
            git_dir = root / 'objects'; git_dir.mkdir()
            env = _git_environment(root)
            env.update(GIT_AUTHOR_NAME='NICO owned fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                GIT_COMMITTER_NAME='NICO owned fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid',
                GIT_AUTHOR_DATE='2026-09-21T00:00:00+00:00', GIT_COMMITTER_DATE='2026-09-21T00:00:00+00:00')
            def git(*argv, data=None):
                return subprocess.run(['git', *argv], cwd=git_dir, env=env, input=data,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=10).stdout.strip().decode()
            git('init', '--bare', '.')
            objects = {path: git('hash-object', '-w', '--stdin', data=raw) for path, raw in SOURCES.items()}
            tree = git('mktree', data=''.join(f'100644 blob {sha}\t{path}\n' for path, sha in sorted(objects.items())).encode())
            revision = git('commit-tree', tree, data=b'Owned analyzer smoke control\n')
            targets = {path: hashlib.sha256(raw).hexdigest() for path, raw in SOURCES.items()}
            materialized = materialize_exact_git_inputs(git_dir=git_dir, commit_sha=revision,
                expected_tree_sha=tree, inputs=targets, destination=root/'source', max_files=2,
                max_file_bytes=1024, max_total_bytes=2048, timeout_seconds=15)
            plan = {'profile': 'cppcheck-standalone-v1', 'tool_version': '2.17.1',
                'image_digest': args.image, 'configuration': CONFIGURATION, 'targets': targets,
                'limits': {'max_attempts': 1, 'wall_seconds': 60, 'lease_seconds': 30},
                'max_receipt_bytes': 1048576}
            def checkpoint():
                if time.monotonic() - start > 60:
                    raise ValueError('owned_control_aggregate_deadline')
            result = run_isolated_cppcheck(plan, root/'source', checkpoint=checkpoint, timeout_seconds=30)
            evidence.update(materialization=materialized, contract=plan, controller=result)
            if result['native_decoding_failed']:
                raise ValueError('native_output_decoding_failed_bytes_retained')
            identity = JobIdentity('owned-ci-control', 'cppcheck-smoke', 'owned-control', 'owned-scan',
                'owned/in-memory-control', revision, _digest(plan), source_sha)
            receipt = {'schema': 'nico.worker-native-receipt.v1', 'identity': asdict(identity),
                'lease_id': 'e'*32, 'worker_id': 'owned-ci-local-validation-not-production-authority',
                'image_digest': args.image, 'tool_version': plan['tool_version'],
                'configuration_sha256': _digest(CONFIGURATION), 'target_hashes': targets,
                'native': result['native'], 'native_sha256': _digest(result['native'])}
            raw, record, _ = validate_receipt(identity, plan, receipt['lease_id'], receipt['worker_id'], receipt)
            evidence.update(receipt=receipt, receipt_sha256=hashlib.sha256(raw).hexdigest(), canonical_record=record)
            assert record['completed'], 'required static targets not complete'
            assert any(f['rule_id']=='nullPointer' and f['path']=='diagnostic.cpp' for f in record['findings'])
            assert not any(f['path']=='clean.cpp' for f in record['findings'])
            assert record['cppcheck_source_coverage']['configuration_aware'] is False
            evidence['status'] = 'PASS_ANALYZER_SMOKE_ONLY'
    except Exception as error:
        evidence.update(status='FAIL', error_type=type(error).__name__)
        raise
    finally:
        evidence['duration_ms'] = int((time.monotonic()-start)*1000)
        evidence['evidence_sha256'] = hashlib.sha256(canonical_bytes(evidence)).hexdigest()
        args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True)+'\n')
        print(json.dumps({'status': evidence['status'], 'artifact': str(args.output)}))


if __name__ == '__main__':
    main()
