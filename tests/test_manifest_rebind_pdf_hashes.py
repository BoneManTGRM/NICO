import base64
from copy import deepcopy
import io

import pytest
from pypdf import PdfReader

from nico.comprehensive_artifact_manifest_approval_v1 import attach_artifact_manifest, rebind_artifact_manifest
from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
from tests.test_comprehensive_artifact_manifest_approval_v1 import _package


@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_preapproval_update_refreshes_visible_pdf_digests_and_preserves_original(language):
    package = _package()
    package['json']['identity']['report_language'] = language
    original = attach_artifact_manifest(package)
    changed = deepcopy(original)
    changed['markdown'] += '\nUpdated technical evidence for review.\n'
    changed['html'] += '<p>Updated technical evidence for review.</p>'
    result = rebind_artifact_manifest(changed)
    text = ''.join(''.join(page.extract_text().split()) for page in PdfReader(io.BytesIO(base64.b64decode(result['pdf_base64']))).pages)
    for item in result['artifact_manifest']['artifacts']:
        if item['artifact_type'] in {'markdown_report', 'html_report', 'findings_csv', 'evidence_csv', 'candidate_register_json', 'remediation_backlog_json'}:
            assert item['sha256'] in text, item['artifact_type']
    assert original['markdown_sha256'] not in text
    assert original['html_sha256'] not in text
    assert result['pdf_sha256'] != original['pdf_sha256']
    assert result['pdf_page_count'] == original['pdf_page_count']
    assert result['client_delivery_allowed'] is False
    _validate_exact_artifact_hashes(result)
    assert changed['pdf_base64'] == original['pdf_base64']


def test_approved_package_is_never_refreshed():
    package = attach_artifact_manifest(_package())
    package['approval_status'] = 'approved_final'
    with pytest.raises(ValueError, match='cannot be rebound'):
        rebind_artifact_manifest(package)


def test_unchanged_digest_table_does_not_rewrite_pdf():
    package = attach_artifact_manifest(_package())
    assert rebind_artifact_manifest(package)['pdf_base64'] == package['pdf_base64']


def test_missing_manifest_page_fails_closed():
    from tests.test_comprehensive_artifact_manifest_approval_v1 import _pdf
    package = attach_artifact_manifest(_package())
    package['pdf_base64'] = base64.b64encode(_pdf()).decode('ascii')
    with pytest.raises(ValueError, match='cannot be identified uniquely'):
        rebind_artifact_manifest(package)
