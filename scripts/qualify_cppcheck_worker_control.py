"""Real isolated analyzer smoke control, not the full C/C++ qualification.

Owned clean/known-diagnostic sources exercise the actual materializer, executor
and canonical receipt validator. No target repository build or human decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from uuid import uuid4

from nico.assessment_worker_container import run_isolated_cppcheck
from nico.assessment_worker_receipts import CONFIGURATION, canonical_bytes
from nico.repository_snapshot import _git_environment

SOURCES = {
    'clean.cpp': b'int add(int a, int b) { return a + b; }\n',
    'diagnostic.cpp': b'int dereference_null() { int* p = nullptr; return *p; }\n',
}

CONFIGURED_SOURCES = {
    'main.cpp': b'#include "value.h"\nint main() { return add_value(2, 3) == 7 ? 0 : 47; }\n',
    'value.cpp': b'#include "value.h"\nint add_value(int a, int b) { return a + b + BIAS; }\n'
                 b'#if BIAS == 2\nint diagnostic() { int* p = nullptr; return *p; }\n'
                 b'#else\nint diagnostic() { return 0; }\n#endif\n',
    'include/value.h': b'#ifndef OWNED_VALUE_H\n#define OWNED_VALUE_H\nint add_value(int, int);\n#endif\n',
}

SANITIZER_SOURCES = {
    'main.cpp': b'#include "value.h"\nint main() { return probe() == 7 ? 0 : 47; }\n',
    'value.cpp': b'#include "value.h"\nint probe() {\n#if TRIGGER && ADDRESS\n'
                 b'  int* values = new int[1]{7}; volatile int index = 1;\n'
                 b'  int result = values[index]; delete[] values; return result;\n'
                 b'#elif TRIGGER\n  volatile int maximum = 2147483647; return maximum + 1;\n'
                 b'#else\n  return 7;\n#endif\n}\n',
    'include/value.h': b'#ifndef OWNED_VALUE_H\n#define OWNED_VALUE_H\nint probe();\n#endif\n',
}


def configured_plan(image, sources=CONFIGURED_SOURCES, bias='2'):
    return {'profile': 'cpp-configured-v1', 'tool_version': '2.17.1', 'image_digest': image,
        'configuration': {'platform': 'unix64', 'compiler_version': '14.2.0',
            'translation_units': [{'path': path, 'language': 'c++', 'standard': 'c++20',
                'defines': {'BIAS': bias}, 'include_dirs': ['include']} for path in ['main.cpp', 'value.cpp']],
            'headers': ['include/value.h']},
        'targets': {path: hashlib.sha256(raw).hexdigest() for path, raw in sources.items()},
        'limits': {'max_attempts': 1, 'wall_seconds': 60, 'lease_seconds': 30}, 'max_receipt_bytes': 1048576}


def sanitizer_plan(image, kind, trigger):
    plan = configured_plan(image, sources=SANITIZER_SOURCES)
    plan['profile'] = 'cpp-sanitized-v1'
    plan['configuration']['sanitizer'] = kind
    for unit in plan['configuration']['translation_units']:
        unit['defines'] = {'ADDRESS': '1' if kind == 'address' else '0', 'TRIGGER': str(int(trigger))}
    return plan



@dataclass
class ControlToken:
    job_id: str
    source_sha: str
    signing_key: bytes

    def __call__(self):
        import jwt
        from nico import assessment_worker_auth as auth
        now = int(time.time())
        return jwt.encode({'iss': auth.ISSUER, 'aud': auth.AUDIENCE + '/' + self.job_id,
            'sub': 'repo:BoneManTGRM/NICO:ref:refs/heads/main', 'iat': now, 'nbf': now,
            'exp': now + 300, 'jti': uuid4().hex, 'repository': 'BoneManTGRM/NICO',
            'repository_id': '123456', 'ref': 'refs/heads/main', 'sha': self.source_sha,
            'workflow_sha': self.source_sha, 'workflow_ref': 'BoneManTGRM/NICO/' + auth.WORKFLOW + '@refs/heads/main',
            'event_name': 'workflow_dispatch', 'run_id': '12345678', 'run_attempt': '1',
            'runner_environment': 'github-hosted'}, self.signing_key, algorithm='RS256')


@contextmanager
def owned_tls_api(client, calls):
    """Loopback TLS lets the real spawned transport exercise the ASGI routes."""
    from datetime import datetime, timedelta, timezone
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import ipaddress
    import socket
    import ssl
    import threading
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import requests

    with tempfile.TemporaryDirectory(prefix='nico-owned-tls-') as temp:
        root = Path(temp)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'owned-control')])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
            .sign(key, hashes.SHA256()))
        cert_path = root / 'cert.pem'; key_path = root / 'key.pem'
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): return
            def do_POST(self):
                size = int(self.headers.get('Content-Length', '-1'))
                if not 0 <= size <= 8 * 1024 * 1024:
                    self.send_error(413); return
                body = self.rfile.read(size)
                operation = self.path.rsplit('/', 1)[-1]
                calls.append((operation, body, self.headers['Authorization']))
                response = client.post(self.path, content=body,
                    headers={'Authorization': self.headers['Authorization'], 'Content-Type': 'application/json'},
                    follow_redirects=False)
                if operation == 'receipt' and sum(op == 'receipt' for op, _, _ in calls) == 1:
                    assert response.status_code == 200
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.close_connection = True
                    return
                self.send_response(response.status_code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(response.content)))
                self.end_headers()
                self.wfile.write(response.content)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert_path, key_path)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        session = requests.Session(); session.trust_env = False; session.verify = str(cert_path)
        try:
            yield 'https://127.0.0.1:' + str(server.server_port), session
        finally:
            session.close(); server.shutdown(); server.server_close(); thread.join(timeout=2)


def consume_control(plan, git_dir, tree, revision, source_sha, evidence):
    """Real consumer, authenticated local HTTP and PostgreSQL; synthetic issuer.

    Only the existing disposable CI database and owned source are used. The
    production verifier's exact-main constraints are unchanged.
    """
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from cryptography.hazmat.primitives import serialization
    from nico import assessment_worker_auth as auth
    from nico.assessment_worker_api import install_assessment_worker_api
    from nico.assessment_worker_consumer import WorkerTransport, consume_one_job, local_git_inputs
    from nico.assessment_worker_jobs import WorkerJobs
    from nico.scanner_raw_artifact_storage_v1 import read_scanner_artifact
    from nico.scanner_worker import get_scan
    from nico.snapshot_scanner_worker import start_snapshot_scan
    from nico.storage import PostgresAdapter, STORE

    STORE.adapter = PostgresAdapter(os.environ['NICO_TEST_DATABASE_URL'])
    os.environ['RAILWAY_GIT_COMMIT_SHA'] = source_sha
    os.environ['NICO_ASSESSMENT_WORKER_REPOSITORY_ID'] = '123456'
    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    auth._jwk_client = lambda: SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=signing_key.public_key()))
    app = FastAPI(); install_assessment_worker_api(app)
    scan = start_snapshot_scan({'authorized': True, 'authorized_by': 'owned_native_control',
        'authorization_scope': 'owned C/C++ native control with frozen source and configuration',
        'repository': 'owned/in-memory-control', 'customer_id': 'owned-ci-control',
        'project_id': 'cppcheck-smoke', 'run_id': 'owned-control-' + uuid4().hex,
        'snapshot_id': 'owned-snapshot', 'snapshot_commit_sha': revision,
        'provider_access_mode': 'anonymous_public', 'provider_credential_used': False}, worker_contract=plan)
    job_id = scan['worker_job_id']
    calls = []

    token = ControlToken(job_id, source_sha, signing_key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    with TestClient(app) as client, owned_tls_api(client, calls) as (backend, session):
        def execute(*args, **kwargs):
            kwargs['timeout_seconds'] = min(30, kwargs['timeout_seconds'])
            result = run_isolated_cppcheck(*args, **kwargs)
            evidence['controller'] = result
            return result

        result = consume_one_job(WorkerTransport(backend, job_id, source_sha, token, session=session), acquire=local_git_inputs(git_dir, tree), execute=execute)
    retained = get_scan(scan['scan_id'])
    record = retained['scanner_results'][0]
    binding = {key: record[key] for key in ('run_id', 'scan_id', 'customer_id', 'project_id', 'repository', 'commit_sha', 'scanner_name')}
    first, second = (read_scanner_artifact(record, binding=binding) for _ in range(2))
    assert first.metadata['availability'] == 'verified' and first.raw == second.raw
    assert hashlib.sha256(first.raw).hexdigest() == result['receipt_sha256']
    assert json.loads(first.raw) == result['receipt']
    receipt_calls = [row for row in calls if row[0] == 'receipt']
    assert len(receipt_calls) == 2 and receipt_calls[0] == receipt_calls[1]
    assert sum(op == 'claim' for op, _, _ in calls) == 1
    job = WorkerJobs(STORE.adapter).get_by_id(job_id)
    assert job['attempts'] == 1 and job['status'] == 'completed'
    assert set(retained['tools_requested']) == {row['tool'] for row in retained['scanner_results']}
    assert all(row['completed'] is False for row in retained['scanner_results'] if row['tool'] != 'cppcheck')
    evidence['consumer_proof'] = {'authenticated_loopback_tls': True, 'spawned_bounded_transport': True, 'synthetic_issuer': True,
        'real_postgres': True, 'lost_receipt_response_idempotent': True,
        'same_bytes_retrieved_twice': True, 'claim_attempts': 1, 'job_id': job_id,
        'production_dispatch_exercised': False, 'source_provisioning': 'owned_preprovisioned_git_objects'}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', type=Path, default=Path('cppcheck-worker-control.json'))
    args = parser.parse_args()
    source_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    evidence = {'schema': 'nico.cppcheck_worker_control.v1', 'status': 'UNPROVEN',
        'source_sha': source_sha, 'tool_source': 'cppcheck-opensource/cppcheck',
        'tool_revision': 'ac9db3069b9f90e81e126a090b99ad456e122cf8',
        'scope': 'owned standalone and configured C/C++ controls; not Bitcoin qualification',
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
            def source_tree(sources):
                def subtree(entries):
                    rows, directories = [], {}
                    for path, raw in sorted(entries.items()):
                        name, sep, rest = path.partition('/')
                        if sep: directories.setdefault(name, {})[rest] = raw
                        else: rows.append(f"100644 blob {git('hash-object', '-w', '--stdin', data=raw)}\t{name}\n")
                    rows += [f'040000 tree {subtree(entries)}\t{name}\n' for name, entries in sorted(directories.items())]
                    return git('mktree', data=''.join(rows).encode())
                return subtree(sources)
            tree = source_tree(SOURCES)
            revision = git('commit-tree', tree, data=b'Owned analyzer smoke control\n')
            targets = {path: hashlib.sha256(raw).hexdigest() for path, raw in SOURCES.items()}
            plan = {'profile': 'cppcheck-standalone-v1', 'tool_version': '2.17.1',
                'image_digest': args.image, 'configuration': CONFIGURATION, 'targets': targets,
                'limits': {'max_attempts': 1, 'wall_seconds': 60, 'lease_seconds': 30},
                'max_receipt_bytes': 1048576}
            result = consume_control(plan, git_dir, tree, revision, source_sha, evidence)
            record = result['canonical_record']
            evidence.update(materialization=result['acquisition'], contract=plan, receipt=result['receipt'],
                receipt_sha256=result['receipt_sha256'], canonical_record=record)
            assert record['completed'], 'required static targets not complete'
            assert any(f['rule_id']=='nullPointer' and f['path']=='diagnostic.cpp' for f in record['findings'])
            assert not any(f['path']=='clean.cpp' for f in record['findings'])
            assert record['cppcheck_source_coverage']['configuration_aware'] is False
            configured_tree = source_tree(CONFIGURED_SOURCES)
            configured_revision = git('commit-tree', configured_tree, data=b'Owned configured C++ control\n')
            configured_evidence = {}
            configured = consume_control(configured_plan(args.image), git_dir, configured_tree,
                configured_revision, source_sha, configured_evidence)
            evidence['configured_control'] = {**configured_evidence, **configured,
                'contract': configured_plan(args.image), 'revision': configured_revision, 'tree': configured_tree}
            configured_record = configured['canonical_record']
            print(json.dumps({'configured_status': configured_record['status'],
                'coverage': configured_record['cppcheck_source_coverage'],
                'build': configured_record['cpp_build_evidence']}, sort_keys=True))
            assert configured_record['completed'], 'configured owned control incomplete'
            assert configured_record['cppcheck_source_coverage']['configuration_aware']
            assert configured_record['cppcheck_source_coverage']['header_context_verified']
            assert configured_record['cpp_build_evidence']['build_completed']
            assert configured_record['cpp_build_evidence']['native_test'] == {'required': 1, 'attempted': 1, 'executed': 1, 'passed': 1}
            assert any(f['rule_id'] == 'nullPointer' and f['path'] == 'value.cpp' for f in configured_record['findings'])
            assert not any(f['path'] == 'main.cpp' for f in configured_record['findings'])
            # Same exact source, only the frozen macro changes. A successful
            # build/analyzer cannot conceal the intentionally failing test.
            negative_evidence = {}
            negative_plan = configured_plan(args.image, bias='3')
            negative = consume_control(negative_plan, git_dir, configured_tree,
                configured_revision, source_sha, negative_evidence)
            evidence['configured_negative'] = {**negative_evidence, **negative, 'contract': negative_plan}
            assert negative['canonical_record']['status'] == 'failed'
            assert negative['canonical_record']['cpp_build_evidence']['build_completed']
            assert negative['canonical_record']['cpp_build_evidence']['native_test']['passed'] == 0
            assert negative['canonical_record']['cpp_build_evidence']['native_test']['executed'] is None
            assert negative['receipt']['native']['steps'][-1]['exit_code'] == 47
            assert not any(f['rule_id'] == 'nullPointer' for f in negative['canonical_record']['findings'])
            evidence.update(compilation_database_verified=True, header_context_verified=True,
                build_runtime_executed=True, status='PASS_OWNED_CONFIGURED_CONTROL')
            sanitizer_tree = source_tree(SANITIZER_SOURCES)
            sanitizer_revision = git('commit-tree', sanitizer_tree, data=b'Owned sanitizer controls\n')
            evidence['sanitizer_controls'] = []
            for kind in ('address', 'undefined'):
                for trigger in (False, True):
                    plan = sanitizer_plan(args.image, kind, trigger)
                    observations = {}
                    result = consume_control(plan, git_dir, sanitizer_tree, sanitizer_revision,
                                             source_sha, observations)
                    evidence['sanitizer_controls'].append({**observations, **result, 'contract': plan,
                        'revision': sanitizer_revision, 'tree': sanitizer_tree, 'owned_trigger': trigger})
                    record = result['canonical_record']
                    sanitizer = record['cpp_build_evidence']['sanitizer']
                    print(json.dumps({'sanitizer': kind, 'owned_trigger': trigger, 'result': sanitizer}, sort_keys=True))
                    assert record['cpp_build_evidence']['build_completed']
                    assert record['cppcheck_source_coverage']['observed_target_count'] == 2
                    assert record['cppcheck_source_coverage']['header_context_verified']
                    assert sanitizer['kind'] == kind
                    if trigger:
                        assert record['status'] == 'failed' and not record['completed']
                        assert sanitizer['outcome'] == 'diagnostic_reported'
                        assert sanitizer['executed'] is None  # generic failed-entry count stays conservative
                        output = result['receipt']['native']['steps'][-1]['stdout']
                        import base64
                        diagnostic = base64.b64decode(output).decode('utf-8')
                        assert ('heap-buffer-overflow' if kind == 'address' else 'signed integer overflow') in diagnostic
                    else:
                        assert record['completed'] and sanitizer['outcome'] == 'clean'
                        assert sanitizer['executed'] == 1
            evidence['status'] = 'PASS_OWNED_SANITIZER_CONTROLS'
    except Exception as error:
        evidence.update(status='FAIL', error_type=type(error).__name__)
        raise
    finally:
        evidence['duration_ms'] = int((time.monotonic()-start)*1000)
        evidence['evidence_sha256'] = hashlib.sha256(canonical_bytes(evidence)).hexdigest()
        args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True)+'\n')
        print(json.dumps({'status': evidence['status'], 'artifact': str(args.output),
            'source_sha': source_sha, 'evidence_sha256': evidence['evidence_sha256'],
            'receipt_sha256': evidence.get('receipt_sha256'), 'consumer_proof': evidence.get('consumer_proof')}))


if __name__ == '__main__':
    main()
