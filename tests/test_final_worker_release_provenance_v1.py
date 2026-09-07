from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_fresh_worker_captures_and_renders_its_own_release_provenance(tmp_path, language):
    # The isolated renderer used to omit the parent's provenance installation.
    # Test real import-time aliases in a fresh process, not a manually installed hook.
    script = textwrap.dedent("""
        import base64, io, os
        from pypdf import PdfReader
        from nico.api import final_report_worker_bootstrap
        from nico.comprehensive_canonical_report_source_v1 import build_canonical_report_source
        from nico import v2_premium_report_renderer as premium
        from nico import comprehensive_spanish_canonical_report_v87 as spanish

        language = os.environ['TEST_REPORT_LANGUAGE']
        context = {
            'run_id': 'comprun_synthetic_provenance',
            'repository': 'BoneManTGRM/NICO',
            'commit_sha': 'c' * 40,
            'evidence_ledger_id': 'ledger_synthetic_provenance',
            'customer_id': 'synthetic_customer',
            'project_id': 'synthetic_project',
            'generated_at': '2026-09-07T00:00:00Z',
            'report_language': language,
            'prior_stage_results': {
                'authorization_and_scope': {
                    'status': 'complete', 'evidence': {'authorized': True},
                },
                'evidence_reconciliation_and_scoring': {
                    'status': 'complete',
                    'assessment': {
                        'technical_score': 80,
                        'canonical_evidence_adjusted_score': 75,
                        'maturity_signal': {
                            'technical_score': 80,
                            'canonical_evidence_adjusted_score': 75,
                            'presented_score': 80,
                        },
                        'sections': [],
                        'human_review_required': True,
                        'client_delivery_allowed': False,
                    },
                    'evidence': {},
                },
            },
        }
        result = build_canonical_report_source(context)
        assert result['status'] == 'complete', result
        canonical = result['report_package']['json']
        provenance = canonical['assessment'].get('nico_release_provenance')
        assert isinstance(provenance, dict), 'isolated canonical source omitted release provenance'
        assert provenance['backend_build_commit'] == 'a' * 40
        assert provenance['frontend_build_commit'] == 'b' * 40
        assert provenance['railway_deployment_id'] == 'synthetic-renderer-deployment'
        assert canonical['identity']['commit_sha'] == 'c' * 40
        assert canonical['human_review_required'] is True
        assert canonical['client_delivery_allowed'] is False

        # A later deployment must not relabel the renderer captured by this source.
        os.environ['RAILWAY_GIT_COMMIT_SHA'] = 'd' * 40

        identity = canonical['identity']
        assessment = canonical['assessment']
        stages = canonical['stage_summaries']
        if language == 'es-MX':
            markdown = spanish.render_spanish_markdown(canonical)
            pdf, pages = spanish.render_spanish_pdf(canonical)
            title = 'Procedencia de la versión de NICO'
            backend_label = 'Commit del código del backend'
            frontend_label = 'Commit del código del frontend'
            scanner_boundary = 'Las versiones de los analizadores son declaraciones de configuración o valores predeterminados'
        else:
            markdown = premium._markdown(identity, assessment, stages, identity['generated_at'])
            encoded, error, pages = premium._pdf(identity, assessment, stages, identity['generated_at'])
            assert not error, error
            pdf = base64.b64decode(encoded)
            title = 'NICO Release Provenance'
            backend_label = 'Backend source commit'
            frontend_label = 'Frontend source commit'
            scanner_boundary = 'Scanner versions are configured or default declarations'
        text = '\\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
        for surface in (markdown, text):
            assert title in surface, (language, 'missing localized provenance title')
            assert backend_label in surface
            assert frontend_label in surface
            assert scanner_boundary in surface
            assert 'a' * 40 in surface
            assert 'b' * 40 in surface
            assert 'c' * 40 in surface
        assert len(PdfReader(io.BytesIO(pdf)).pages) == pages
        assert text.count(title) == 1, 'provenance appendix was duplicated'
        assert 'd' * 40 not in text
        from nico.comprehensive_release_provenance_v1 import install_comprehensive_release_provenance
        install_comprehensive_release_provenance()
        if language == 'es-MX':
            repeated_pdf, repeated_pages = spanish.render_spanish_pdf(canonical)
        else:
            repeated_encoded, repeated_error, repeated_pages = premium._pdf(
                identity, assessment, stages, identity['generated_at'],
            )
            assert not repeated_error, repeated_error
            repeated_pdf = base64.b64decode(repeated_encoded)
        repeated_text = '\\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(repeated_pdf)).pages)
        assert repeated_pages == pages
        assert repeated_text == text, 'reinstallation changed retained provenance'
        from pathlib import Path
        Path(os.environ['TEST_REPORT_OUTPUT']).write_bytes(pdf)

        # Verify the complete production composition retains the captured source,
        # not merely the low-level renderer helpers before later PDF transforms.
        from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
        composed = rebuild_client_artifacts(result['report_package'])
        composed_pdf = base64.b64decode(composed['pdf_base64'])
        composed_text = '\\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(composed_pdf)).pages)
        assert composed['json']['assessment']['nico_release_provenance'] == provenance
        assert composed['json']['identity']['commit_sha'] == 'c' * 40
        assert title in composed_text
        assert all(commit * 40 in composed_text for commit in ('a', 'b', 'c'))
        assert 'd' * 40 not in composed_text
        print('verified worker canonical source and locale renderer', language)
    """)
    root = Path(__file__).resolve().parents[1]
    environment = {
        key: os.environ[key] for key in ("PATH", "LANG", "SYSTEMROOT") if key in os.environ
    }
    environment.update({
        "PYTHONPATH": str(root),
        "NICO_HOME": str(tmp_path),
        "NICO_SQLITE_PATH": str(tmp_path / "nico.sqlite3"),
        "RAILWAY_GIT_COMMIT_SHA": "a" * 40,
        "NICO_RELEASE_COMMIT_SHA": "a" * 40,
        "NICO_FRONTEND_BUILD_COMMIT_SHA": "b" * 40,
        "RAILWAY_DEPLOYMENT_ID": "synthetic-renderer-deployment",
        "TEST_REPORT_LANGUAGE": language,
        "TEST_REPORT_OUTPUT": str(tmp_path / f"synthetic-provenance-{language}.pdf"),
    })
    completed = subprocess.run(
        [sys.executable, "-c", script], cwd=root, env=environment,
        capture_output=True, text=True, timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
