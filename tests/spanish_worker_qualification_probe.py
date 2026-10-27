"""Synthetic full-worker/Phase17 probe, executed only by qualification tests."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import time
from copy import deepcopy
from pathlib import Path


def _enrich_owned_fixture(package):
    """Add bounded display and machine literals through supported contracts."""
    from nico.comprehensive_engagement_metadata_v1 import build_comprehensive_engagement_metadata

    fields = {
        'client_name': 'Compañía Águila',
        'project_name': 'Proyecto Ñandú',
        'primary_technical_contact': 'María-José Pérez',
        'access_method': 'https://example.invalid/owned/repository',
        'authorized_scope': 'apps/web/app/page.tsx:100; if (ready) { return value; }',
    }
    engagement = build_comprehensive_engagement_metadata(
        client_name=fields['client_name'], project_name=fields['project_name'],
        human_evidence={'stakeholder_context': {'evidence': {
            key: [fields[key]] for key in ('primary_technical_contact', 'access_method', 'authorized_scope')
        }}},
    )
    package['json']['engagement_metadata'] = engagement
    package['json']['identity'].update(
        customer_name=fields['client_name'], project_name=fields['project_name'],
        primary_technical_contact=fields['primary_technical_contact'],
        access_method=fields['access_method'], authorized_scope=fields['authorized_scope'],
        engagement_metadata_sha256=engagement['engagement_metadata_sha256'],
    )
    # Phase17's complexity-hotspot policy classifies this bounded fixture as P2.
    # Supply that canonical value so the retention assertion is meaningful.
    package['json']['canonical_findings'][0].update(finding_id='RISK-P2-QUAL-001', priority='P2')
    return [*fields.values(), 'RISK-P2-QUAL-001']


def observe():
    # First application import: actual child renderer startup, never web bootstrap.
    from nico.api import final_report_worker_bootstrap as worker
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _artifact_content
    from nico.comprehensive_same_run_locale_report_v1 import canonical_sha256, _assessment_truth_projection
    from tests.test_v2_premium_report_renderer import _package
    from pypdf import PdfReader

    state = worker.FINAL_REPORT_WORKER_RUNTIME
    assert state['same_terminal_report_authority_as_production'] is True
    assert state['nested_renderer_orchestration_installed'] is False
    assert not hasattr(worker.app.state, 'nico_final_report_process_isolation')
    observations = {}
    bilingual_truth = {}
    rich = os.environ.get('NICO_TEST_WORKER_RICH_FIXTURE') == '1'
    export_root = Path(os.environ['NICO_TEST_WORKER_EXPORT']) if rich else None
    if export_root is not None:
        export_root.mkdir(parents=True, exist_ok=True)
    for language in ('en', 'es-MX'):
        package = _package(language)
        literals = _enrich_owned_fixture(package) if rich else []
        before = deepcopy(package)
        completed = []
        durations = []
        for _ in range(2):
            started = time.monotonic()
            result = rebuild_client_artifacts(package)
            durations.append(round(time.monotonic() - started, 3))
            assert package == before
            _validate_exact_artifact_hashes(result)
            assert result['canonical_truth_sha256'] == canonical_sha256(result['json'])
            assert result['human_review_required'] is True
            assert result['client_delivery_allowed'] is False
            assert result['approval_status'] == 'pending_human_approval'
            assert result['delivery_status'] == 'blocked_pending_human_approval'
            assert result['json']['identity']['run_id'] == before['json']['identity']['run_id']
            assert result['json']['identity']['commit_sha'] == before['json']['identity']['commit_sha']
            assert result['json']['identity']['report_language'] == language
            pdf = base64.b64decode(result['pdf_base64'], validate=True)
            reader = PdfReader(io.BytesIO(pdf))
            assert len(reader.pages) == result['pdf_page_count']
            assert reader.outline
            texts = [page.extract_text() or '' for page in reader.pages]
            assert all(text.strip() for text in texts)
            for page in reader.pages:
                assert float(page.mediabox.width) > 0 and float(page.mediabox.height) > 0
            if rich:
                compact = lambda value: ''.join(value.split())
                for literal in literals:
                    for surface in (result['markdown'], '\n'.join(texts)):
                        assert compact(literal) in compact(surface), (language, literal)
                identity = result['json']['identity']
                for key in ('repository', 'evidence_ledger_id', 'customer_id', 'project_id', 'generated_at'):
                    assert identity[key] == before['json']['identity'][key], key
                source_findings = before['json']['canonical_findings']
                rendered_findings = result['json']['canonical_findings']
                assert [(f['finding_id'], f['priority'], f['location']) for f in rendered_findings] == [
                    (f['finding_id'], f['priority'], f['location']) for f in source_findings
                ], (source_findings, rendered_findings)
                for key in ('technical_score', 'canonical_evidence_adjusted_score'):
                    assert result['json']['assessment'][key] == before['json']['assessment'][key], key
                source_scanners = before['json']['scanner_execution_records']
                output_scanners = result['json']['scanner_execution_records']
                assert len(output_scanners) == len(source_scanners)
                scanner_additions = {}
                for source_scanner, output_scanner in zip(source_scanners, output_scanners, strict=True):
                    # Reconciliation adds applicability/provenance metadata; every
                    # original raw field, including findings and hash, must survive.
                    assert {key: output_scanner[key] for key in source_scanner} == source_scanner
                    scanner_additions[source_scanner['scanner_name']] = {
                        key: value for key, value in output_scanner.items() if key not in source_scanner
                    }
                truth = _assessment_truth_projection(result['json'])
                if language in bilingual_truth:
                    assert bilingual_truth[language] == truth
                bilingual_truth[language] = truth
                # Compare every manifest artifact's exact bytes, not only rendered PDF text.
                artifacts = {
                    item['artifact_type']: base64.b64encode(_artifact_content(result, item['artifact_type'])[0]).decode('ascii')
                    for item in result['artifact_manifest']['artifacts']
                }
                snapshot = {
                    'artifacts': artifacts, 'manifest': result['artifact_manifest'],
                    'canonical': result['json'], 'literals': literals,
                    'canonical_truth_sha256': result['canonical_truth_sha256'],
                    'scanner_reconciliation_additions': scanner_additions,
                }
                destination = export_root / (language + '.json')
                if destination.exists():
                    assert json.loads(destination.read_text()) == snapshot, language
                else:
                    destination.write_text(json.dumps(snapshot, sort_keys=True), encoding='utf-8')
            completed.append({
                'pdf_sha256': hashlib.sha256(pdf).hexdigest(),
                'markdown_sha256': hashlib.sha256(result['markdown'].encode()).hexdigest(),
                'html_sha256': hashlib.sha256(result['html'].encode()).hexdigest(),
                'canonical_truth_sha256': result['canonical_truth_sha256'],
                'pages': len(reader.pages),
            })
            time.sleep(1.05)
        assert completed[0] == completed[1], (language, completed)
        observations[language] = {'artifacts': completed[0], 'render_seconds': durations}
    if rich:
        assert bilingual_truth['en'] == bilingual_truth['es-MX'], bilingual_truth
    print('NICO_WORKER_QUALIFICATION=' + json.dumps(observations, sort_keys=True))


if __name__ == '__main__':
    observe()
