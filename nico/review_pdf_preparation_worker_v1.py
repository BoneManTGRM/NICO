"""Dormant isolated retained-review renderer; no routes, assessments or schema setup."""
from __future__ import annotations

import base64
from dataclasses import asdict
from contextlib import contextmanager
from threading import Event, Thread
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from nico.review_pdf_preparation_deadline_v1 import DeadlineGuard
from nico.review_pdf_artifact_policy_v1 import artifact_mode, validate_headers, SOURCE

from nico.comprehensive_final_report_process_worker_v1 import (
    _atomic_json, terminate_process, _PROCESS_GROUP_ATTR,
)


_CONNECTION_ATTEMPTS = 0


def validate_result(result, identity, *, parse_pdf=True):
    from pypdf import PdfReader
    if not isinstance(result, dict) or set(result) != {'pdf_base64', 'headers', 'identity', 'validated_page_count'}:
        raise ValueError('review_pdf_invalid_result')
    if result['identity'] != asdict(identity):
        raise ValueError('review_pdf_worker_identity_invalid')
    headers = result['headers']
    expected = {
        'x-nico-run-id': identity.run_id,
        'x-nico-commit-sha': identity.commit_sha,
        'x-nico-report-language': identity.language,
        'x-nico-canonical-truth-sha256': identity.canonical_truth_sha256,
        'x-nico-assessment-rerun': 'false',
        'x-nico-approval-status': 'pending_human_approval',
        'x-nico-client-delivery-allowed': 'false',
        'x-nico-delivery-status': 'blocked_pending_human_approval',
    }
    if (not isinstance(headers, dict) or any(headers.get(k) != v for k, v in expected.items())
            or headers.get('x-nico-accepted-pdf-sha256')):
        raise ValueError('review_pdf_result_binding_invalid')
    validate_headers(headers, identity.artifact_mode)
    encoded = result['pdf_base64']
    if not isinstance(encoded, str) or len(encoded) > 64 * 1024 * 1024:
        raise ValueError('review_pdf_result_size_invalid')
    pdf = base64.b64decode(encoded, validate=True)
    digest = hashlib.sha256(pdf).hexdigest()
    if (not pdf.startswith(b'%PDF') or headers.get('x-nico-pdf-sha256') != digest
            or headers.get('x-nico-artifact-sha256') != digest):
        raise ValueError('review_pdf_checksum_invalid')
    if type(result['validated_page_count']) is not int or result['validated_page_count'] < 1:
        raise ValueError('review_pdf_validation_missing')
    if not parse_pdf:
        return pdf, digest
    reader = PdfReader(io.BytesIO(pdf), strict=True)
    if reader.is_encrypted or len(reader.pages) != result['validated_page_count']:
        raise ValueError('review_pdf_pages_invalid')
    # Force parsing/extraction of every page; no abbreviated PDF is assembled here.
    for page in reader.pages:
        page.extract_text()
    return pdf, digest


def child_build(context, *, verifying=None):
    import sqlite3
    import psycopg
    import socket
    def forbidden_connection(*args, **kwargs):
        global _CONNECTION_ATTEMPTS
        _CONNECTION_ATTEMPTS += 1
        raise RuntimeError('review_pdf_child_connection_forbidden')
    sqlite3.connect = psycopg.connect = socket.create_connection = forbidden_connection
    # This full entrypoint supplies the existing production locale wrapper chain.
    # Parent strips database configuration before this fresh interpreter starts.
    from nico.api import specialist_ship_ready_bootstrap  # noqa: F401
    from nico.comprehensive_same_run_locale_report_v1 import build_same_run_locale_pdf_response
    mode = artifact_mode(context['status'], context['language'])
    if mode != context['identity']['artifact_mode']:
        raise ValueError('review_pdf_worker_artifact_mode_changed')
    response = build_same_run_locale_pdf_response(context['status'], context['language'])
    response.headers['x-nico-review-pdf-artifact-mode'] = mode
    if mode == SOURCE and 'x-nico-localized-artifact-approval-invalidated' not in response.headers:
        response.headers['x-nico-localized-artifact-approval-invalidated'] = 'false'
    if verifying is not None:
        verifying()
    from pypdf import PdfReader
    from nico.review_pdf_preparation_jobs_v1 import PreparationIdentity
    pages = len(PdfReader(io.BytesIO(response.body), strict=True).pages)
    result = {'pdf_base64': base64.b64encode(response.body).decode('ascii'),
              'headers': dict(response.headers), 'identity': context['identity'],
              'validated_page_count': pages}
    validate_result(result, PreparationIdentity(**context['identity']))
    if _CONNECTION_ATTEMPTS:
        raise RuntimeError('review_pdf_child_connection_attempted')
    return result


@contextmanager
def _owned_directory(guard, state):
    directory = tempfile.TemporaryDirectory(prefix='nico-review-pdf-')
    state['temporary_files_cleanup_confirmed'] = False
    try:
        yield directory.name
    finally:
        def cleanup():
            # A bounded-call timeout is not physical file-operation completion.
            while not guard.idle() or not state.get('physical_worker_exit_confirmed', True):
                Event().wait(.02)
            directory.cleanup()
            state['temporary_files_cleanup_confirmed'] = True
        if guard.idle() and state.get('physical_worker_exit_confirmed', True):
            cleanup()
        else:
            Thread(target=cleanup, daemon=True, name='nico-review-private-file-cleanup').start()


def run_worker(status, identity, *, stop, heartbeat, state, max_seconds):
    if not 0 < max_seconds <= 900:
        raise ValueError('review_pdf_worker_budget_invalid')
    env = {k: v for k, v in os.environ.items() if not (
        k.startswith('PG') or k in {'DATABASE_URL', 'DATABASE_PRIVATE_URL', 'POSTGRES_URL',
            'POSTGRES_PRIVATE_URL', 'RAILWAY_DATABASE_URL', 'RAILWAY_POSTGRES_URL'})}
    env.update(NICO_DISABLE_POSTGRES='true', NICO_ENABLE_SQLITE_DURABLE_STORAGE='false',
               NICO_REQUIRE_DURABLE_ASSESSMENT_STORAGE='false')
    process = None
    started = time.monotonic()
    guard = DeadlineGuard(max_seconds, stop, clock=time.monotonic)
    state.setdefault("pending_guards", []).append(guard)
    with _owned_directory(guard, state) as directory:
        root = Path(directory)
        try:
            guard.call(_atomic_json, root / 'input.json', {'status': status, 'language': identity.language, 'identity': asdict(identity)})
            guard.check()
            if stop.is_set():
                raise RuntimeError('review_pdf_cancelled')
            state['physical_worker_exit_confirmed'] = False
            process = subprocess.Popen([sys.executable, '-m', __name__, str(root)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=env, close_fds=True, start_new_session=os.name == 'posix')
            if os.name == 'posix':
                setattr(process, _PROCESS_GROUP_ATTR, process.pid)
            last_heartbeat = 0.
            while process.poll() is None:
                now = time.monotonic()
                if stop.is_set() or now - started >= max_seconds:
                    raise RuntimeError('review_pdf_cancelled_or_expired')
                if now - last_heartbeat >= 5:
                    phase_path = root / 'phase.json'
                    if (phase_path.exists() and phase_path.stat().st_size < 200
                            and json.loads(phase_path.read_text()) == {'phase': 'verifying'}):
                        guard.call(heartbeat, phase='verifying', timeout=5)
                    else:
                        guard.call(heartbeat, timeout=5)
                    last_heartbeat = now
                stop.wait(.1)
            if stop.is_set() or time.monotonic() - started >= max_seconds:
                raise RuntimeError('review_pdf_cancelled_or_expired')
            if process.returncode != 0:
                raise RuntimeError('review_pdf_builder_failed')
            output = root / 'output.json'
            if output.stat().st_size > 65 * 1024 * 1024:
                raise ValueError('review_pdf_result_size_invalid')
            return guard.call(lambda: json.loads(output.read_text()))
        finally:
            guard.stop.set()
            state['physical_worker_exit_confirmed'] = False
            state['physical_worker_exit_confirmed'] = process is None or terminate_process(process)
            if not state['physical_worker_exit_confirmed']:
                raise RuntimeError('review_pdf_worker_termination_unconfirmed')


if __name__ == '__main__':
    root = Path(sys.argv[1])
    _atomic_json(root / 'output.json', child_build(json.loads((root / 'input.json').read_text()),
        verifying=lambda: _atomic_json(root / 'phase.json', {'phase': 'verifying'})))
