"""Historical locale representations must not trigger new rendering."""
import base64
from copy import deepcopy
import io
import zipfile

import pytest

from nico import comprehensive_same_run_locale_report_v1 as locale
from nico.comprehensive_localized_export_v1 import localized_evidence_package
from nico.comprehensive_exact_artifact_hash_binding_v1 import _artifact_bytes
from nico.comprehensive_retained_report_export_v1 import retained_report_zip


@pytest.fixture(scope='module')
def frozen_spanish():
    from tests.test_v2_premium_report_renderer import _package
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    reports = rebuild_client_artifacts(_package('es-MX'))
    canonical = reports['json']
    reports['report_id'] = canonical.get('report_id') or 'report_frozen_spanish_alias_fixture'
    reports['canonical_truth_sha256'] = locale.canonical_sha256(canonical)
    return {**{key: canonical['identity'][key] for key in
               ('run_id', 'repository', 'commit_sha', 'evidence_ledger_id')},
            'report_language': 'es-MX', 'terminal': True, 'reports': reports}


@pytest.mark.parametrize('location,value', [('identity', 'ES_mx'), ('identity', 'es_mx'), ('canonical', 'es-MX')])
def test_frozen_aliases_preserve_markdown_pdf_and_zip(monkeypatch, frozen_spanish, location, value):
    from nico.comprehensive_artifact_manifest_approval_v1 import rebind_artifact_manifest
    status = deepcopy(frozen_spanish)
    canonical = status['reports']['json']
    for section in (canonical, canonical['identity'], canonical['assessment']):
        section.pop('report_language', None)
        section.pop('locale', None)
    (canonical['identity'] if location == 'identity' else canonical)['report_language'] = value
    # Construct the historical pending fixture with real exact-hash binding,
    # then freeze it. No validator or rendering hook is bypassed below.
    status['reports'] = rebind_artifact_manifest(status['reports'])
    reports = status['reports']
    reports['canonical_truth_sha256'] = locale.canonical_sha256(reports['json'])
    before = deepcopy(status)
    expected_zip = retained_report_zip(reports)
    def forbidden(*args, **kwargs):
        pytest.fail('Frozen alias triggered rendering')
    for name in ('_render_target', '_assemble_target', '_pdf', 'render_spanish_pdf'):
        monkeypatch.setattr(locale, name, forbidden)
    for _ in range(2):
        markdown = locale.build_same_run_locale_markdown_projection(status, 'es-MX')
        pdf = locale.build_same_run_locale_pdf_response(status, 'es-MX')
        archive = localized_evidence_package(status, 'es-MX')
        assert markdown['report']['markdown'] == reports['markdown']
        assert markdown['localized_artifact_requires_new_approval'] is False
        assert pdf.body == base64.b64decode(reports['pdf_base64'])
        assert archive.body == expected_zip
        with zipfile.ZipFile(io.BytesIO(archive.body)) as zipped:
            for entry in reports['artifact_manifest']['artifacts']:
                assert zipped.read(entry['filename']) == _artifact_bytes(reports, entry['artifact_type'])
        assert archive.headers['x-nico-client-delivery-allowed'] == 'false'
    assert status == before


@pytest.mark.parametrize('section,field', [
    ('identity', 'report_language'), ('identity', 'locale'),
    ('canonical', 'report_language'), ('canonical', 'locale'),
    ('assessment', 'report_language'), ('assessment', 'locale'),
])
def test_all_source_locale_locations_keep_frozen_markdown_and_pdf(monkeypatch, section, field):
    from tests.test_frozen_source_pdf_readonly_work_v1 import _status
    status, pdf_bytes = _status('es-MX')
    canonical = status['reports']['json']
    for item in (canonical, canonical['identity'], canonical['assessment']):
        item.pop('report_language', None)
        item.pop('locale', None)
    (canonical if section == 'canonical' else canonical[section])[field] = 'ES_mx'
    status['reports']['canonical_truth_sha256'] = locale.canonical_sha256(canonical)
    before = deepcopy(status)
    def forbidden(*args, **kwargs):
        pytest.fail('Frozen source locale triggered rendering')
    monkeypatch.setattr(locale, '_render_target', forbidden)
    monkeypatch.setattr(locale, '_assemble_target', forbidden)
    assert locale.build_same_run_locale_markdown_projection(status, 'es-MX')['report']['markdown'] == status['reports']['markdown']
    assert locale.build_same_run_locale_pdf_response(status, 'es-MX').body == pdf_bytes
    assert status == before
    canonical['assessment']['technical_score'] = 91
    for builder in (locale.build_same_run_locale_markdown_projection, locale.build_same_run_locale_pdf_response, localized_evidence_package):
        with pytest.raises(ValueError, match='canonical_truth_hash_mismatch'):
            builder(status, 'es-MX')
