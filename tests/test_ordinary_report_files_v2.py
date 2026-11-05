import base64
from copy import deepcopy
import io
import json
import zipfile

import pytest
from pypdf import PdfReader

from nico import ordinary_report_files_v2 as files
from nico import ordinary_review_bundle_v2 as core
from nico.client_pdf_compose_v2 import compose_compact_client_pdf, compose_review_bundle
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from tests.test_client_pdf_compose_v2 import _pdf


def inputs(locale='en', pages=65):
    identity = {'run_id':'comprun_transport', 'repository':'owner/repo', 'commit_sha':'a'*40,
                'report_language':locale}
    canonical = {'identity':deepcopy(identity), 'client_delivery_allowed':False,
                 'human_review_required':True, 'approval_status':'pending_human_approval',
                 'report_finality':'automated_draft', 'assessment':{'score':93}}
    identity['canonical_truth_sha256'] = canonical_sha256(canonical)
    exports = {kind: 'retained '+kind+'\n' for kind in files.EXPORT_NAMES}
    exports['canonical_json'] = core._json(canonical).decode()
    exports['candidate_register_json'] = '{"findings":[]}'
    exports['remediation_backlog_json'] = '{"items":[]}'
    components = dict(base_pdf=_pdf(*[[f'PRIMARY_{i:03d}'] for i in range(pages)]),
                      register_pdf=_pdf(['REGISTER_REQUIRED']), gate_pdf=_pdf(['GATE_REQUIRED']),
                      review_pdf=_pdf(['WORKSHEET_REQUIRED']), ci_boundary_pdf=_pdf(['CI_REQUIRED']),
                      human_evidence_pdf=_pdf(['HUMAN_REQUIRED']))
    return identity, exports, components


def make_family(locale='en'):
    identity, exports, components = inputs(locale)
    bundle = compose_review_bundle(identity, **components)
    family = files.build_report_files(bundle, exports, expected_identity=identity,
                                      expected_bundle_manifest_sha256=bundle['manifest_sha256'])
    return identity, family


@pytest.fixture(scope='module')
def frozen():
    return make_family()


def kwargs(identity, family):
    return dict(expected_identity=identity, expected_manifest_sha256=family['manifest_sha256'])


@pytest.mark.parametrize('locale', ['en','es-MX'])
def test_complete_composition_and_frozen_family_roundtrip(locale):
    identity, exports, components = inputs(locale)
    saved = deepcopy((identity,exports,components))
    ordinary = PdfReader(io.BytesIO(compose_compact_client_pdf(**components)))
    assert len(ordinary.pages) == 70
    ordinary_text = '\n'.join(page.extract_text() for page in ordinary.pages)
    for n in range(65):
        assert ordinary_text.count(f'PRIMARY_{n:03d}') == 1
    for marker in ('REGISTER_REQUIRED','GATE_REQUIRED','WORKSHEET_REQUIRED','CI_REQUIRED','HUMAN_REQUIRED'):
        assert ordinary_text.count(marker) == 1
    with pytest.raises(ValueError, match='cannot preserve every primary'):
        compose_compact_client_pdf(**components, page_limit=60)
    bundle = compose_review_bundle(identity, **components)
    text = ''
    for volume, file in zip(bundle['manifest']['volumes'],bundle['files']):
        reader = PdfReader(io.BytesIO(base64.b64decode(file['pdf_base64'])))
        assert len(reader.pages) <= 60
        text += '\n'.join(page.extract_text() for page in reader.pages[volume['index_pages']:])
    for n in range(65): assert text.count(f'PRIMARY_{n:03d}') == 1
    for marker in ('REGISTER_REQUIRED','GATE_REQUIRED','WORKSHEET_REQUIRED','CI_REQUIRED','HUMAN_REQUIRED'):
        assert text.count(marker) == 1
    assert bundle['manifest']['source_page_count'] == 70
    family = files.build_report_files(bundle,exports,expected_identity=identity,
                                      expected_bundle_manifest_sha256=bundle['manifest_sha256'])
    archive = files.report_files_zip(family, **kwargs(identity,family))
    assert archive == files.report_files_zip(family, **kwargs(identity,family))
    assert files.read_report_files_zip(archive, **kwargs(identity,family)) == family
    assert (identity,exports,components) == saved
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        for kind, filename in files.EXPORT_NAMES.items(): assert zipped.read(filename) == exports[kind].encode()
        assert len(zipped.namelist()) == len(bundle['files']) + 10


@pytest.mark.parametrize('damage', ['missing','extra','duplicate','swap','unsafe','reserved','tamper','first_only','schema'])
def test_family_member_controls(frozen, damage):
    identity, original = frozen; family = deepcopy(original)
    if damage == 'missing': family['files'].pop(0)
    if damage == 'extra': family['files'].append(deepcopy(family['files'][0]))
    if damage == 'duplicate': family['files'][1] = deepcopy(family['files'][0])
    if damage == 'swap': family['files'][0],family['files'][1] = family['files'][1],family['files'][0]
    if damage == 'unsafe': family['files'][0]['filename'] = '../volume-001-en.pdf'
    if damage == 'reserved': family['files'][0]['filename'] = files.MANIFEST_NAME
    if damage == 'tamper': family['files'][0]['content_base64'] = base64.b64encode(_pdf(['different'])).decode()
    if damage == 'first_only': family['files'] = family['files'][:1]
    if damage == 'schema': family['artifact_schema'] = 'nico.ordinary-report-files.v1'
    with pytest.raises(ValueError): files.validate_report_files(family, **kwargs(identity, original))


@pytest.mark.parametrize('field,value', [('run_id','another'),('repository','other/repo'),('commit_sha','c'*40),
                                         ('canonical_truth_sha256','d'*64),('report_language','es-MX')])
def test_identity_binding(frozen, field, value):
    identity, family = frozen; identity=deepcopy(identity);identity[field]=value
    with pytest.raises(ValueError): files.validate_report_files(family, **kwargs(identity,family))


def rewrite_zip(data, mutate):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries=[(item.filename,archive.read(item.filename)) for item in archive.infolist()]
    mutate(entries)
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as archive:
        for name,raw in entries: archive.writestr(name,raw)
    return out.getvalue()


@pytest.mark.parametrize('damage',['missing','extra','duplicate','same_name_changed','unsafe','reserved','reorder','undeclared'])
def test_archive_exact_population(frozen, damage):
    identity,family=frozen; archive=files.report_files_zip(family,**kwargs(identity,family))
    def mutate(entries):
        if damage=='missing': entries.pop()
        if damage=='extra': entries.append(('extra.pdf',_pdf(['extra'])))
        if damage=='duplicate': entries.append(entries[-1])
        if damage=='same_name_changed': entries[-1]=(entries[-1][0],_pdf(['substituted']))
        if damage=='unsafe': entries[-1]=('../'+entries[-1][0],entries[-1][1])
        if damage=='reserved': entries[-1]=(files.MANIFEST_NAME,entries[-1][1])
        if damage=='reorder': entries.reverse()
        if damage=='undeclared': entries[-1]=('undeclared.pdf',entries[-1][1])
    with pytest.raises(ValueError):
        files.read_report_files_zip(rewrite_zip(archive,mutate),**kwargs(identity,family))


def test_changed_member_cannot_reuse_retained_identity(frozen):
    identity, original=frozen; family=deepcopy(original)
    entry=next(e for e in family['manifest']['artifacts'] if e['artifact_type']=='markdown_report')
    raw=b'changed report text'
    next(f for f in family['files'] if f['filename']==entry['filename'])['content_base64']=base64.b64encode(raw).decode()
    entry.update(sha256=core._sha(raw),size_bytes=len(raw))
    family['manifest_sha256']=core._sha(core._json(family['manifest']))
    with pytest.raises(ValueError,match='manifest_digest'):
        files.validate_report_files(family,**kwargs(identity,original))


def test_canonical_cannot_disagree_with_source_or_review_authority():
    identity,exports,components=inputs(pages=1)
    bundle=compose_review_bundle(identity,**components)
    canonical=json.loads(exports['canonical_json']);canonical['assessment']['score']=100
    exports['canonical_json']=core._json(canonical).decode()
    with pytest.raises(ValueError,match='canonical_truth'):
        files.build_report_files(bundle,exports,expected_identity=identity,expected_bundle_manifest_sha256=bundle['manifest_sha256'])


@pytest.mark.parametrize('limit',['MAX_FAMILY_BYTES','MAX_TEXT_BYTES'])
def test_transport_limits_fail_closed(frozen,monkeypatch,limit):
    identity,family=frozen;monkeypatch.setattr(files,limit,1)
    with pytest.raises(ValueError,match='limit'):files.report_files_zip(family,**kwargs(identity,family))


def test_required_components_cannot_be_omitted():
    identity,_,components=inputs(pages=1);components['review_pdf']=None
    with pytest.raises(ValueError,match='required_component_missing'):compose_review_bundle(identity,**components)
