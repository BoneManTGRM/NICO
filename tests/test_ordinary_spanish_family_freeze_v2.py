import base64
from copy import deepcopy
import io

import pytest
from pypdf import PdfReader, PdfWriter
from nico import ordinary_spanish_family_freeze_v2 as subject
from nico import ordinary_review_bundle_v2 as core
from nico import ordinary_report_files_v2 as transport
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from tests.test_client_pdf_compose_v2 import _pdf


def inputs(pages=65):
    from nico.client_report_completion_v2 import _REVIEW_SECTION_TITLES_ES
    from nico.comprehensive_ci_boundary_compat_v74 import ci_cd_boundary_markers
    identity = {'run_id':'comprun_family_fixture','repository':'fixture/repository',
                'commit_sha':'a'*40,'report_language':'es-MX'}
    canonical = {'identity':identity,'human_review_required':True,'human_review_completed':False,
                 'client_delivery_allowed':False,'approval_status':'pending_human_approval',
                 'report_finality':'automated_draft','canonical_findings':[], 'assessment':{'score':93}}
    source = deepcopy(canonical);source['identity']['report_language']='en'
    register = {'summary':{'finding_population_reconciled':True,
        'semantic_duplicate_code_anchors_absent':True,
        'scanner_configuration_errors_promoted_to_code_findings':False,
        'unverified_tls_candidates_promoted_to_p1':False,'stable_alias_projection_idempotent':True,
        'decision_finding_count':0},'code_findings':[]}
    required = ['BORRADOR AUTOMATIZADO',*_REVIEW_SECTION_TITLES_ES,
                *ci_cd_boundary_markers(canonical,spanish=True)]
    exports = {kind:'fixture\n' for kind in transport.EXPORT_NAMES}
    exports.update(canonical_json=core._json(canonical).decode(),
                   candidate_register_json='{"findings":[]}',remediation_backlog_json='{"items":[]}',
                   markdown_report='\n'.join(required),html_report='<p>'+'</p><p>'.join(required)+'</p>')
    components = dict(base_pdf=_pdf(*[[f'PRIMARY_{i:03d}', 'BORRADOR AUTOMATIZADO'] for i in range(pages)]),
        review_pdf=_pdf(*[required[i:i+8] for i in range(0,len(required),8)]),
        register_pdf=_pdf(['REGISTER_REQUIRED']),gate_pdf=_pdf(['GATE_REQUIRED']),
        ci_boundary_pdf=_pdf(ci_cd_boundary_markers(canonical,spanish=True)),
        human_evidence_pdf=_pdf(['HUMAN_REQUIRED']))
    return dict(source_canonical=source,expected_source_truth_sha256=canonical_sha256(source),
                localized_canonical=canonical,register=register,exports=exports,components=components)


def test_complete_final_family_navigation_semantics_and_distinct_digests():
    args=inputs();before=deepcopy(args)
    frozen=subject.finalize_spanish_review_family(**args)
    receipt=frozen['receipt'];identity=receipt['identity']
    assert receipt['source_truth_sha256'] != receipt['locale_canonical_truth_sha256']
    assert receipt['semantic_validation']['finding_population_reconciled'] is True
    members=transport._validated_members(frozen['report_bundle'],identity,receipt['family_manifest_sha256'])
    text=''
    for name,data in members.items():
        if name.endswith('.pdf'):
            reader=PdfReader(io.BytesIO(data));assert len(reader.pages)<=60
            assert reader.outline and reader.page_labels==[str(i) for i in range(1,len(reader.pages)+1)]
            text+='\n'.join(p.extract_text() for p in reader.pages)
    for i in range(65):assert text.count(f'PRIMARY_{i:03d}')==1
    for value in ('REGISTER_REQUIRED','GATE_REQUIRED','HUMAN_REQUIRED'):assert text.count(value)==1
    assert args==before
    assert args['localized_canonical']['human_review_completed'] is False
    assert frozen['report_bundle']['manifest']['client_delivery_allowed'] is False


@pytest.mark.parametrize('failure',['missing','duplicate','reordered','partial'])
def test_construction_cannot_change_independent_selected_page_inventory(monkeypatch,failure):
    args=inputs();original=core.build_review_bundle
    def broken(identity,sections):
        if failure=='partial':raise RuntimeError('interrupted construction')
        sections=list(sections)
        name,data=sections[0];reader=PdfReader(io.BytesIO(data));pages=list(reader.pages)
        if failure=='missing':pages.pop()
        if failure=='duplicate':pages[-1]=pages[0]
        if failure=='reordered':pages[0],pages[1]=pages[1],pages[0]
        writer=PdfWriter()
        for page in pages:writer.add_page(page)
        out=io.BytesIO();writer.write(out);sections[0]=(name,out.getvalue())
        return original(identity,sections)
    monkeypatch.setattr(core,'build_review_bundle',broken)
    with pytest.raises((ValueError,RuntimeError),match='selected_page_inventory|interrupted'):
        subject.finalize_spanish_review_family(**args)


@pytest.mark.parametrize('failure',['component','source','locale','canonical_bytes','approval','semantic','limit'])
def test_failed_inputs_do_not_freeze_or_mutate(monkeypatch,failure):
    args=inputs()
    if failure=='component':args['components'].pop('gate_pdf')
    elif failure=='source':args['expected_source_truth_sha256']='b'*64
    elif failure=='locale':args['localized_canonical']['identity']['report_language']='en'
    elif failure=='canonical_bytes':args['exports']['canonical_json']='{}'
    elif failure=='approval':
        args['localized_canonical']['client_delivery_allowed']=True
        args['exports']['canonical_json']=core._json(args['localized_canonical']).decode()
    elif failure=='semantic':args['register']['summary']['finding_population_reconciled']=False
    else:args['components']['base_pdf']=_pdf(*[['BOUND'] for _ in range(481)])
    before=deepcopy(args)
    def forbidden(*a,**k):raise AssertionError('family must not freeze')
    monkeypatch.setattr(transport,'build_report_files',forbidden)
    with pytest.raises(ValueError):subject.finalize_spanish_review_family(**args)
    assert args==before


def test_late_family_mutation_and_installed_single_pdf_finalizer_rejected():
    args=inputs(2);frozen=subject.finalize_spanish_review_family(**args)
    from nico import client_report_completion_v2 as completion
    from nico.comprehensive_artifact_manifest_approval_v1 import install_comprehensive_artifact_manifest_approval_v1
    from nico.comprehensive_client_report_render_v60 import install_comprehensive_client_report_render_v60
    install_comprehensive_client_report_render_v60()
    install_comprehensive_artifact_manifest_approval_v1()
    assert hasattr(completion.finalize_client_report_package, '_nico_previous')
    # Installed wrapper chain must reach the legacy boundary without accepting v2.
    with pytest.raises(ValueError,match='report_bundle_requires_v2_boundary'):
        completion.finalize_client_report_package(frozen)
    frozen['report_bundle']['files'].pop()
    with pytest.raises(ValueError):subject.validate_frozen_spanish_family(frozen,
        expected_source_truth_sha256=args['expected_source_truth_sha256'],
        expected_identity=frozen['receipt']['identity'],expected_receipt_sha256=frozen['receipt_sha256'])


def test_missing_pdf_semantics_cannot_be_supplied_only_by_text_exports():
    args=inputs(2)
    args['components']['review_pdf']=_pdf(['BORRADOR AUTOMATIZADO'])
    with pytest.raises(ValueError,match='pdf_review_sections_missing'):
        subject.finalize_spanish_review_family(**args)


def test_partial_file_family_construction_returns_nothing(monkeypatch):
    args=inputs(2);before=deepcopy(args);original=transport.build_report_files
    def interrupted(*a,**k):
        original(*a,**k)
        raise RuntimeError('interrupted family freeze')
    monkeypatch.setattr(transport,'build_report_files',interrupted)
    with pytest.raises(RuntimeError,match='interrupted family freeze'):
        subject.finalize_spanish_review_family(**args)
    assert args==before


def test_navigation_tampering_after_construction_is_not_frozen(monkeypatch):
    original=core.build_review_bundle
    def broken(*a,**k):
        result=original(*a,**k)
        file=result['files'][0];reader=PdfReader(io.BytesIO(base64.b64decode(file['pdf_base64'])))
        writer=PdfWriter()
        for page in reader.pages:writer.add_page(page)
        # Same visible pages, but the required navigation and labels are gone.
        out=io.BytesIO();writer.write(out);data=out.getvalue()
        file['pdf_base64']=base64.b64encode(data).decode()
        result['manifest']['volumes'][0].update(sha256=core._sha(data),size_bytes=len(data))
        result['manifest_sha256']=core._sha(core._json(result['manifest']))
        return result
    monkeypatch.setattr(core,'build_review_bundle',broken)
    with pytest.raises(ValueError,match='bundle_navigation'):
        subject.finalize_spanish_review_family(**inputs(2))
