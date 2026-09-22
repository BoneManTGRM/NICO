"""Actual owned-project consumer/receipt/report proof, not production acceptance.

Reuses the existing PostgreSQL/TLS worker protocol control. Its issuer is
synthetic; no production dispatch, actual provider OIDC, or Bitcoin is implied.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from nico.assessment_cpp_full_project import PROFILE, configuration
from nico.assessment_worker_receipts import canonical_bytes
from nico.repository_snapshot import _git_environment
from scripts.qualify_cpp_full_project_control import FIXTURE
from scripts.qualify_cppcheck_worker_control import consume_control


def plan(image, *, negative=False):
    return {'profile': PROFILE, 'tool_version': '2.17.1', 'image_digest': image,
        'configuration': configuration(units=['main.cpp', 'sum.cpp'],
            unit_tests=['negative' if negative else 'unit'], integration_tests=['integration']),
        'targets': {path: hashlib.sha256(text.encode()).hexdigest() for path, text in FIXTURE.items()},
        'limits': {'max_attempts': 1, 'wall_seconds': 180, 'lease_seconds': 30},
        'max_receipt_bytes': 2 * 1024 * 1024}


def render_result(result, output, language):
    """Use the normal client exporter with a clearly labeled owned proof context."""
    from pypdf import PdfReader
    from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from tests.test_v2_premium_report_renderer import _package
    package = _package(language)
    canonical = package['json']
    record = result.get('persisted_record', result['canonical_record'])
    canonical['identity'].update(repository=record['repository'], commit_sha=record['commit_sha'],
        run_id=record['run_id'], customer_id=record['customer_id'], project_id=record['project_id'])
    canonical['canonical_findings'] = []
    canonical['roadmap'] = []
    canonical['assessment'].update(sections=[], maturity_signal={}, technical_score=None,
        canonical_evidence_adjusted_score=None,
        unavailable_data_notes=[('Prueba de integración con código propio; no es una evaluación de producción.'
            if language == 'es-MX' else 'Owned integration proof only; not a production assessment.')])
    compact = compact_scanner_records({'scan_id': record['scan_id'], 'scanner_results': [record]}, commit_sha=record['commit_sha'])
    canonical['scanner_execution_records'] = compact
    rendered = rebuild_client_artifacts(package)
    stem = 'owned-project-' + language
    pdf = base64.b64decode(rendered['pdf_base64'])
    text = '\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(pdf)).pages)
    phrase = 'C/C++ project execution' if language == 'en' else 'Ejecución del proyecto C/C++'
    # All formats must expose the same project result, not just the nested JSON.
    assert phrase in rendered['markdown'], 'project_summary_missing_in_markdown'
    assert phrase in rendered['html'], 'project_summary_missing_in_html'
    assert phrase in text, 'project_summary_missing_in_pdf'
    assert rendered['report_finality'] == 'automated_draft'
    assert rendered['human_review_required'] is True
    for key, raw in [('pdf', pdf), ('md', rendered['markdown'].encode()), ('html', rendered['html'].encode()),
                     ('json', canonical_bytes(rendered['json']))]:
        (output / (stem + '.' + key)).write_bytes(raw)
    return {'language': language, 'summary_in_all_formats': True,
        'pdf_sha256': hashlib.sha256(pdf).hexdigest(), 'pdf_page_count': len(PdfReader(io.BytesIO(pdf)).pages),
        'automated_draft': True, 'production_report': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', type=Path, default=Path('cpp-full-project-integration'))
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    release = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    evidence = {'schema': 'nico.cpp-project-integration-control.v1', 'source_sha': release,
        'status': 'UNPROVEN', 'synthetic_issuer': True, 'production_dispatch_exercised': False,
        'production_qualified': False, 'bitcoin_executed': False, 'controls': [], 'reports': []}
    start = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='nico-project-owned-') as temporary:
            root = Path(temporary); git_dir = root / 'objects'; git_dir.mkdir()
            env = _git_environment(root)
            env.update(GIT_AUTHOR_NAME='NICO owned fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                GIT_COMMITTER_NAME='NICO owned fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid',
                GIT_AUTHOR_DATE='2026-09-22T00:00:00+00:00', GIT_COMMITTER_DATE='2026-09-22T00:00:00+00:00')
            def git(*argv, data=None):
                return subprocess.run(['git', *argv], cwd=git_dir, env=env, input=data,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=10).stdout.strip().decode()
            git('init', '--bare', '.')
            rows = [f"100644 blob {git('hash-object', '-w', '--stdin', data=text.encode())}\t{path}\n"
                    for path, text in sorted(FIXTURE.items())]
            tree = git('mktree', data=''.join(rows).encode())
            revision = git('commit-tree', tree, data=b'Owned CMake integration fixture\n')
            for negative in (False, True):
                contract = plan(args.image, negative=negative); observations = {}
                result = consume_control(contract, git_dir, tree, revision, release, observations)
                from nico.scanner_worker import get_scan
                persisted = get_scan(result['canonical_record']['scan_id'])
                result['persisted_record'] = next(r for r in persisted['scanner_results'] if r.get('tool') == 'cppcheck')
                evidence['controls'].append({**observations, **result, 'contract': contract, 'negative': negative})
                record = result['canonical_record']; build = record['cpp_build_evidence']
                assert record['completed'] is True, 'configuration_aware_static_analysis_incomplete'
                assert build['build_completed'] is True, 'project_build_incomplete'
                assert build['source_read_only_verified'] is True
                assert build['implemented_command_scope_complete'] is (not negative), 'test_truth_changed'
                assert build['requested_scope_complete'] is False
                assert build['fuzz_executed'] is False and build['full_project_qualified'] is False
                assert record['client_delivery_allowed'] is False
                if negative:
                    row = next(r for r in build['stages'] if r['id'] == 'baseline-unit')
                    assert row['status'] == 'failed' and row['exit_code'] == 8
                    assert row['executed_tests'] == ['negative'] and row['passed_tests'] == []
                    for language in ('en', 'es-MX'):
                        evidence['reports'].append(render_result(result, args.output, language))
        evidence['status'] = 'PASS_OWNED_PROJECT_INTEGRATION'
    except Exception as exc:
        # The owned proof may expose an assertion name, never arbitrary tool/transport text.
        evidence['error_type'] = type(exc).__name__
        if isinstance(exc, AssertionError) and str(exc).replace('_', '').isalnum():
            evidence['failed_predicate'] = str(exc)
        raise
    finally:
        evidence['duration_ms'] = int((time.monotonic() - start) * 1000)
        (args.output / 'receipt.json').write_bytes(canonical_bytes(evidence))
        print(json.dumps({k: evidence[k] for k in ('status', 'duration_ms', 'production_qualified', 'bitcoin_executed')}))


if __name__ == '__main__':
    main()
