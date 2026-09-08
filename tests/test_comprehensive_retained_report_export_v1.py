import hashlib
import io
import json
import zipfile
from copy import deepcopy

import pytest

from nico.comprehensive_retained_report_export_v1 import retained_report_zip


def package():
    # Fixed byte fixtures: serialization, whitespace and non-ASCII must survive.
    texts = {'markdown': '# Test\r\n\nEspañol\n', 'html': '<p>Español</p>\n',
             'canonical_json': '{"z":1, "a":"México"}\n',
             'findings_csv': 'id,title\r\n', 'evidence_csv': 'id,source\r\n',
             'candidate_register_json': '[]\n', 'remediation_backlog_json': '[]\n'}
    mapping = {'markdown_report': 'markdown', 'html_report': 'html',
               'canonical_json': 'canonical_json', 'findings_csv': 'findings_csv',
               'evidence_csv': 'evidence_csv', 'candidate_register_json': 'candidate_register_json',
               'remediation_backlog_json': 'remediation_backlog_json'}
    artifacts = [{'artifact_type': kind, 'filename': kind + '.txt',
                  'sha256': hashlib.sha256(texts[key].encode()).hexdigest()}
                 for kind, key in mapping.items()]
    import base64
    pdf = b'%PDF-1.4\nretained bytes\n%%EOF\n'
    artifacts.append({'artifact_type': 'comprehensive_pdf', 'filename': 'report.pdf',
                      'sha256': hashlib.sha256(pdf).hexdigest()})
    manifest = json.dumps({'artifacts': artifacts}, ensure_ascii=False)
    return {**texts, 'pdf_base64': base64.b64encode(pdf).decode(),
            'evidence_manifest_json': manifest,
            'evidence_manifest_sha256': hashlib.sha256(manifest.encode()).hexdigest(),
            'draft_artifact_identity': {'report_finality': 'automated_draft'}}


def test_exports_exact_retained_bytes_without_rendering_or_mutation():
    report = package()
    before = deepcopy(report)
    data = retained_report_zip(report)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        manifest = json.loads(archive.read('evidence-manifest.json'))
        for item in manifest['artifacts']:
            assert hashlib.sha256(archive.read(item['filename'])).hexdigest() == item['sha256']
        assert archive.read('markdown_report.txt') == report['markdown'].encode()
        assert archive.read('canonical_json.txt') == report['canonical_json'].encode()
        assert archive.read('evidence-manifest.json') == report['evidence_manifest_json'].encode()
    assert report == before
    assert retained_report_zip(report) == data


@pytest.mark.parametrize('field', ['markdown', 'html', 'canonical_json', 'evidence_manifest_json'])
def test_tampered_or_missing_bytes_fail_closed(field):
    for value in ('tampered', ''):
        report = package()
        report[field] = value
        with pytest.raises(ValueError):
            retained_report_zip(report)


@pytest.mark.parametrize('filename', ['../report.json', '/report.json', 'a\\report.json',
                                       'evidence-manifest.json', 'report.pdf'])
def test_unsafe_or_duplicate_member_names_fail_closed(filename):
    report = package()
    manifest = json.loads(report['evidence_manifest_json'])
    manifest['artifacts'][0]['filename'] = filename
    report['evidence_manifest_json'] = json.dumps(manifest)
    report['evidence_manifest_sha256'] = hashlib.sha256(report['evidence_manifest_json'].encode()).hexdigest()
    with pytest.raises(ValueError):
        retained_report_zip(report)


def test_authenticated_route_exports_retained_package_and_rejects_tampering(monkeypatch):
    from fastapi.testclient import TestClient
    from nico import comprehensive_artifact_manifest_approval_v1 as manifest
    from nico.comprehensive_exact_artifact_hash_binding_v1 import install_comprehensive_exact_artifact_hash_binding_v1
    from nico.specialist_access_v1 import install_specialist_access, issue_specialist_session, PRODUCTION_PROOF_SCOPE
    from tests.test_comprehensive_artifact_manifest_approval_v1 import _package
    from tests.test_comprehensive_mobile_recovery_v1 import _record, _app

    install_comprehensive_exact_artifact_hash_binding_v1()
    record = _record()
    source = _package()
    source['json']['identity'].update(deepcopy(record['identity']))
    report = manifest.attach_artifact_manifest(source)
    from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
    report['canonical_truth_sha256'] = canonical_sha256(report['json'])
    record['stage_results']['final_comprehensive_report_generation']['report_package'] = report
    before = deepcopy(record)
    app = _app(record)
    install_specialist_access(app)
    monkeypatch.setenv('NICO_COMPREHENSIVE_OPERATOR_PASSWORD', 'internal-export-test-password')
    monkeypatch.setenv('NICO_OPERATOR_SESSION_SIGNING_SECRET', 'internal-export-test-signing-key-with-entropy')
    client = TestClient(app)
    path = '/assessment/comprehensive-run/comprun_mobile_recovery_001/report/evidence-package'
    for target in (path, path.replace('comprun_mobile_recovery_001', 'comprun_unknown')):
        denial = client.get(target)
        assert denial.status_code == 401
        assert 'comprun_' not in denial.text
    assert client.get(path, headers={'X-NICO-Admin-Token': 'wrong'}).status_code == 403
    proof, _ = issue_specialist_session(
        {'authority': 'github_actions_production_proof'}, scope=PRODUCTION_PROOF_SCOPE,
        retained_claims={'repository': 'BoneManTGRM/NICO', 'ref': 'refs/heads/main',
                         'sha': 'b' * 40, 'workflow_ref': 'internal-test.yml',
                         'run_id': '123', 'run_attempt': '1'},
    )
    assert client.get(path, headers={'X-NICO-Operator-Session': proof}).status_code == 403
    response = client.get(path, headers={'X-NICO-Admin-Token': 'internal-export-test-password'})
    assert response.status_code == 200, response.text[:200] if response.status_code != 200 else ''
    assert response.content == retained_report_zip(report)
    assert response.headers['x-nico-artifact-sha256'] == hashlib.sha256(response.content).hexdigest()
    assert response.headers['x-nico-approval-status'] == 'pending_human_approval'
    assert response.headers['x-nico-client-delivery-allowed'] == 'false'
    assert record == before
    report['markdown'] += '\nmaterial change'
    assert client.get(path, headers={'X-NICO-Admin-Token': 'internal-export-test-password'}).status_code == 409
