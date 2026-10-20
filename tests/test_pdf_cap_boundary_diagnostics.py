import base64
from contextvars import copy_context
import hashlib
import json

import pytest

from nico import pdf_cap_failure_diagnostics as diagnostics
from nico.comprehensive_final_report_compact_base_v1 import _COMPACT_FINAL_PDF, _compact_pdf_call
from test_client_pdf_compose_v2 import _pdf


def failure():
    return diagnostics.attach_pdf_cap_diagnostic(ValueError('original'), reason='pdf_required_pages_limit',
        reflow_attempted=False, counts=dict(page_limit=60,base_pages=1,
        retained_body_pages_before_reflow=1,retained_body_pages_after_reflow=1,
        register_pages=60,gate_pages=1,review_pages=0,ci_boundary_pages=0,
        human_evidence_pages=0,required_pages=61,total_pages=62))


def trace():
    return failure().pdf_cap_diagnostic.get('boundary_trace',{})


def test_first_latest_counts_and_attempt_reset():
    pdfs=[_pdf([str(i)]) for i in range(3)]
    with diagnostics.pdf_cap_identity('comprun_'+'a'*32):
        for pdf in pdfs: diagnostics.record_pdf_boundary('premium_return',pdf)
        data=trace()['premium_return']
        assert data['calls']==3
        assert data['first']=={'pages':1,'sha256':hashlib.sha256(pdfs[0]).hexdigest()}
        assert data['latest']=={'pages':1,'sha256':hashlib.sha256(pdfs[-1]).hexdigest()}
        child=copy_context()
        child.run(diagnostics.record_pdf_boundary,'premium_return',pdfs[0])
        assert trace()['premium_return']['calls']==3
        with pytest.raises(ValueError), diagnostics.pdf_cap_identity('nested'):
            assert trace()=={}
            raise ValueError('nested')
        assert trace()['premium_return']['calls']==3
    assert trace()=={}


def test_actual_compact_arguments_preserve_order_and_effective_stages():
    from collections import OrderedDict
    stages=[{'b':2,'a':1}]
    received=[]
    def original(identity,assessment,actual_stages,date,**options):
        received.append(actual_stages)
        return ('unchanged',None,7)
    with diagnostics.pdf_cap_identity('run'):
        assert _compact_pdf_call(original,{'b':2,'a':1},{},stages,'date')==('unchanged',None,7)
        first=trace()['render_arguments']['first']
        token=_COMPACT_FINAL_PDF.set(True)
        try: _compact_pdf_call(original,OrderedDict(a=1,b=2),{},stages,'date')
        finally: _COMPACT_FINAL_PDF.reset(token)
        latest=trace()['render_arguments']['latest']
        assert first['identity_sha256']!=latest['identity_sha256']
        assert first['compact_final_pdf'] is False and latest['compact_final_pdf'] is True
        assert first['supplied_stage_count']==latest['supplied_stage_count']==1
        assert first['effective_stage_count']==1 and latest['effective_stage_count']==0
        assert latest['effective_stages_sha256']==hashlib.sha256(b'[]').hexdigest()
        assert received==[stages,[]]


@pytest.mark.parametrize('damage',[{'pages':True,'sha256':'a'*64},{'pages':-1,'sha256':'a'*64},
    {'pages':1,'sha256':'secret/path'},{'pages':1000001,'sha256':'a'*64}])
def test_malformed_boundary_metadata_rejected(damage):
    data=failure().pdf_cap_diagnostic
    data['boundary_trace']={'premium_return':{'calls':1,'first':damage,'latest':damage}}
    assert diagnostics.sanitize_pdf_cap_diagnostic(data) is None


def test_bad_diagnostic_inputs_do_not_replace_original_error(monkeypatch):
    with diagnostics.pdf_cap_identity('run'):
        diagnostics.record_pdf_boundary('premium_return',b'not pdf')
        diagnostics.record_pdf_boundary('unknown',b'secret')
        diagnostics.record_render_arguments({'secret':object()},{},[],[],False)
        assert trace()=={}
        original=ValueError('renderer failure')
        def fail(*args,**kwargs): raise original
        with pytest.raises(ValueError) as caught:
            _compact_pdf_call(fail,{'secret':object()},{},[],'date')
        assert caught.value is original


def test_composer_success_bytes_unchanged_and_no_trace_leak(caplog):
    from nico.client_pdf_compose_v2 import compose_compact_client_pdf
    base=_pdf(['Executive Decision Brief']); part=_pdf(['Required'])
    expected=compose_compact_client_pdf(base,part,part)
    with diagnostics.pdf_cap_identity('run'):
        actual=compose_compact_client_pdf(base,part,part)
        assert trace()['composer_input']['latest']=={'pages':1,'sha256':hashlib.sha256(base).hexdigest()}
    assert actual==expected
    assert trace()=={}


def test_real_boundary_hooks_capture_quality_repair_and_sanitizer_continuity(monkeypatch):
    from nico import phase17_canonical_artifact_rebuild_v1 as rebuild
    from nico import client_report_completion_v2 as completion
    from nico.client_pdf_compose_v2 import compose_compact_client_pdf
    premium=_pdf(['premium'])
    quality=_pdf(['quality'],['second'])
    sanitized=_pdf(['sanitized'],['second'],['third'])
    register=_pdf(*[['required'] for _ in range(60)])
    gate=_pdf(['gate'])
    def package(pdf):
        return {'json':{},'pdf_base64':base64.b64encode(pdf).decode(),'markdown':'','html':''}
    monkeypatch.setattr(rebuild,'_prepare_client_artifact_package',lambda p:p)
    monkeypatch.setattr(rebuild,'rebuild_single_pass_premium_artifacts',lambda p:package(premium))
    monkeypatch.setattr(rebuild,'repair_rendered_report',lambda p:package(quality))
    monkeypatch.setattr(rebuild,'_reconcile',lambda p:p)
    monkeypatch.setattr(rebuild,'_phase2_review_truth_node',lambda p:p)
    seen=[]
    def sanitizer(pdf):
        seen.append(pdf)
        return sanitized
    monkeypatch.setattr(rebuild,'sanitize_client_pdf_status',sanitizer)
    monkeypatch.setattr(rebuild,'_rewrite_phase2_review_truth_pdf',lambda pdf:pdf)
    monkeypatch.setattr(rebuild,'_reassert_terminal_report_language_authority',lambda:None)
    monkeypatch.setattr(completion,'finalize_client_report_package',lambda p:
        compose_compact_client_pdf(base64.b64decode(p['pdf_base64']),register,gate))
    with diagnostics.pdf_cap_identity('comprun_'+'b'*32), pytest.raises(ValueError) as caught:
        rebuild.rebuild_client_artifacts(package(premium))
    assert str(caught.value)=='client-ready PDF required pages exceed the 60-page boundary'
    data=caught.value.pdf_cap_diagnostic['boundary_trace']
    assert seen==[quality]
    for name,pdf,pages in [('premium_return',premium,1),('sanitizer_input',quality,2),
                           ('sanitizer_output',sanitized,3),('composer_input',sanitized,3)]:
        expected={'pages':pages,'sha256':hashlib.sha256(pdf).hexdigest()}
        assert data[name]=={'calls':1,'first':expected,'latest':expected}
    assert len(json.dumps(data))<2000
    assert diagnostics._TRACE.get() is None


@pytest.mark.parametrize('mutation', ['unknown_boundary','extra_text','bad_count','bool_count','bad_flag','extra_argument'])
def test_trace_schema_never_accepts_arbitrary_values(mutation):
    with diagnostics.pdf_cap_identity('run'):
        diagnostics.record_render_arguments({}, {}, [], [], False)
        data=failure().pdf_cap_diagnostic
    value=data['boundary_trace']
    if mutation=='unknown_boundary': value['secret/path']={}
    elif mutation=='extra_text': value['render_arguments']['raw']='SECRET'
    elif mutation=='bad_count': value['render_arguments']['calls']=1000001
    elif mutation=='bool_count': value['render_arguments']['calls']=True
    elif mutation=='bad_flag': value['render_arguments']['latest']['compact_final_pdf']='false'
    else: value['render_arguments']['first']['identity']='SECRET'
    assert diagnostics.sanitize_pdf_cap_diagnostic(data) is None


def test_hash_budget_and_parser_failure_are_nonfatal(monkeypatch):
    monkeypatch.setattr(diagnostics,'_HASH_LIMIT',4)
    with diagnostics.pdf_cap_identity('run'):
        diagnostics.record_render_arguments({'text':'SECRET'},{},[],[],False)
        assert trace()=={}
        import pypdf
        monkeypatch.setattr(pypdf,'PdfReader',lambda *a,**k: (_ for _ in ()).throw(RuntimeError('SECRET')))
        diagnostics.record_pdf_boundary('premium_return',b'%PDF-invalid')
        assert trace()=={}


@pytest.mark.parametrize('value,limit', [
    ('small scalar', '_JSON_SCALAR_LIMIT'),
    ({'long key': 1}, '_JSON_SCALAR_LIMIT'),
    ([0, 0, 0], '_JSON_NODE_LIMIT'),
    ([[[0]]], '_JSON_DEPTH_LIMIT'),
    ('escaped\ntext', '_HASH_LIMIT'),
])
def test_json_preflight_rejects_before_encoder(monkeypatch, value, limit):
    monkeypatch.setattr(diagnostics, limit, 2)
    def forbidden(*args, **kwargs):
        pytest.fail('encoder must not run for rejected input')
    monkeypatch.setattr(json.JSONEncoder, 'iterencode', forbidden)
    with diagnostics.pdf_cap_identity('run'):
        diagnostics.record_render_arguments(value, {}, [], [], False)
        assert diagnostics._TRACE.get() == {}


@pytest.mark.parametrize('value', [2**257, float('inf'), {1: 'value'}, object()])
def test_unsupported_json_skips_encoding(monkeypatch, value):
    monkeypatch.setattr(json.JSONEncoder, 'iterencode', lambda *a, **k: pytest.fail('encoded unsupported input'))
    with diagnostics.pdf_cap_identity('run'):
        diagnostics.record_render_arguments(value, {}, [], [], False)
        assert diagnostics._TRACE.get() == {}


def test_json_cycles_and_custom_container_hooks_are_not_executed(monkeypatch):
    class CustomDict(dict):
        def items(self):
            pytest.fail('custom container hook executed')
    cyclic = []
    cyclic.append(cyclic)
    monkeypatch.setattr(diagnostics, '_JSON_DEPTH_LIMIT', 3)
    with diagnostics.pdf_cap_identity('run'):
        for value in (cyclic, CustomDict(secret=1)):
            diagnostics.record_render_arguments(value, {}, [], [], False)
            assert diagnostics._TRACE.get() == {}


def test_supported_json_hash_matches_existing_ordered_encoding():
    value = {'z': ['\U0001f600', '\n', None, False, 2.5], 'a': {'v': 1}}
    expected = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode()
    assert diagnostics._ordered_hash(value) == hashlib.sha256(expected).hexdigest()


def test_pdf_size_guards_precede_decode_and_parse(monkeypatch):
    import pypdf
    monkeypatch.setattr(diagnostics, '_PDF_BYTE_LIMIT', 6)
    monkeypatch.setattr(base64, 'b64decode', lambda *a, **k: pytest.fail('decoded oversized input'))
    monkeypatch.setattr(pypdf, 'PdfReader', lambda *a, **k: pytest.fail('parsed oversized input'))
    with diagnostics.pdf_cap_identity('run'):
        diagnostics.record_pdf_boundary('premium_return', 'A' * 12, encoded=True)
        diagnostics.record_pdf_boundary('premium_return', b'A' * 12, encoded=True)
        diagnostics.record_pdf_boundary('premium_return', b'%PDF-too-long')
        diagnostics.record_pdf_boundary('composer_input', b'%PDF-too-long', pages=1)
        assert diagnostics._TRACE.get() == {}


def test_pdf_decoded_size_and_known_page_limit_precede_parser(monkeypatch):
    import pypdf
    # Six decoded bytes fit the base64 length ceiling for a five-byte budget.
    monkeypatch.setattr(diagnostics, '_PDF_BYTE_LIMIT', 5)
    monkeypatch.setattr(diagnostics, '_PDF_PAGE_LIMIT', 2)
    encoded = base64.b64encode(b'%PDF-x')
    monkeypatch.setattr(pypdf, 'PdfReader', lambda *a, **k: pytest.fail('parsed rejected input'))
    with diagnostics.pdf_cap_identity('run'):
        diagnostics.record_pdf_boundary('premium_return', encoded, encoded=True)
        diagnostics.record_pdf_boundary('composer_input', b'%PDF-', pages=3)
        diagnostics.record_pdf_boundary('composer_input', b'%PDF-', pages=True)
        assert diagnostics._TRACE.get() == {}


def test_omitted_oversized_arguments_preserve_success_and_original_error(monkeypatch):
    monkeypatch.setattr(diagnostics, '_JSON_SCALAR_LIMIT', 2)
    with diagnostics.pdf_cap_identity('run'):
        result = object()
        assert _compact_pdf_call(lambda *a, **k: result, {'big': 'text'}, {}, [], 'date') is result
        original = ValueError('original')
        def fail(*a, **k):
            raise original
        with pytest.raises(ValueError) as caught:
            _compact_pdf_call(fail, {'big': 'text'}, {}, [], 'date')
        assert caught.value is original
        assert diagnostics._TRACE.get() == {}


def test_full_runtime_english_premium_call_records_actual_arguments():
    """Separate cold process prevents prior test installer order hiding alias gaps."""
    import os
    import subprocess
    import sys
    code = r'''
import sys, os, tempfile
# Initialize dependency capability/cache checks before the no-side-effect guard.
import urllib3.util.connection
tempfile.tempdir = '/tmp'
sys.dont_write_bytecode = True
class Blocked(BaseException): pass
def audit(event, args):
    if (event.startswith(('socket.', 'sqlite3.connect', 'subprocess.'))
            or event in ('os.system', 'os.posix_spawn', 'os.fork', 'os.mkdir', 'os.remove', 'os.rename')):
        raise Blocked(event)
    if event == 'open':
        _, mode, flags = args
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            raise Blocked('filesystem_write')
sys.addaudithook(audit)
import nico.api.final_report_worker_bootstrap
from nico import v2_premium_report_renderer as premium
from nico import v2_production_authority as authority
from nico import pdf_cap_failure_diagnostics as diagnostics
from nico.comprehensive_final_report_compact_base_v1 import _COMPACT_FINAL_PDF
from reportlab import rl_config
rl_config.invariant = 1
package = {'json': {'identity': {'repository': 'synthetic', 'generated_at': '2026-01-01T00:00:00Z'},
                    'assessment': {}, 'stage_summaries': []}}
for warm in (False, True):
    if warm: authority._reassert_terminal_report_language_authority()
    for compact in (False, True):
        token = _COMPACT_FINAL_PDF.set(compact)
        try:
            expected = premium.rebuild_premium_client_artifacts(package)
            with diagnostics.pdf_cap_identity('synthetic'):
                actual = premium.rebuild_premium_client_artifacts(package)
                observation = diagnostics._TRACE.get()['premium_render_arguments']
                assert observation['calls'] == 1
                item = observation['latest']
                assert item['compact_final_pdf'] is compact
                assert item['effective_stage_count'] == item['supplied_stage_count']
                assert item['effective_stages_sha256'] == item['supplied_stages_sha256']
                assert actual['pdf_base64'] == expected['pdf_base64']
                assert actual == expected
            assert diagnostics._TRACE.get() is None
        finally: _COMPACT_FINAL_PDF.reset(token)
print('cold/warm premium actual call: unchanged output, observed arguments, both compact flags')
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                            timeout=60, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    assert result.returncode == 0, result.stderr
    assert 'cold/warm premium actual call' in result.stdout
