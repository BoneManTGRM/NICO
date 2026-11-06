"""Fresh baseline subphase evidence never implies complete qualification."""
import json
from pathlib import Path
import pytest
from scripts import cpp_template_probe as probe
from scripts import build_cpp_phase_boundaries as build
from scripts import fresh_cpp_phase_diagnostic as fresh
from tests.test_native_template_subphases import sparse_record


def summarize(raw,**kwargs):
    return probe.summarize_prefix(raw,binary_sha256='a'*64,timed_out=True,output_truncated=False,**kwargs)


def test_fresh_prefix_has_explicit_attribution_and_age_limits():
    first=sparse_record(active_bucket=1,bucket_depth=1,selection_entered=1,transition_id=1)
    second=sparse_record(2,active_bucket=1,bucket_depth=1,selection_entered=1,transition_id=1,
        interval_kind=1,interval_ns=20,stable_selection_ns=20,observer_ns=2,selection_visits=100)
    value=summarize(first+second)
    assert value['state']=='observed_prefix' and value['records']==2
    assert value['stable_selection_ns']==20 and value['last_interval_deltas']['selection_visits']==100
    assert value['sample_age_state']=='unavailable' and not value['precise_termination_hotspot_known']
    assert 'prefix_tail_unknown' in value['cpu_attribution']
    assert probe.valid_summary(value)
    assert 'original_binary_sha256' not in value
    assert 'outside_ns' in value and 'using_time' not in value


@pytest.mark.parametrize('raw,state',[(b'','unavailable'),(b'x'*65537,'unavailable'),
    (b'NICO_STAGE_V3 private-secret\n','invalid'),(sparse_record()[:-1],'invalid'),
    (sparse_record(seq=2),'invalid'),(sparse_record()+sparse_record(),'invalid'),
    (sparse_record(stable_selection_ns=2),'invalid'),
    (b''.join(sparse_record(seq=i) for i in range(1,129)),'capped')])
def test_malformed_partial_out_of_order_capped_remain_unknown(raw,state):
    value=summarize(raw)
    assert value==probe.unknown_summary(state)
    assert probe.valid_summary(value)


def test_truncated_output_unknown_even_with_valid_prefix():
    assert probe.summarize_prefix(sparse_record(),binary_sha256='a'*64,timed_out=True,
        output_truncated=True)==probe.unknown_summary('truncated')


@pytest.mark.parametrize('field,value',[('pass',True),('active_bucket',5),('interval_kind',8),('thread_clock_status',0),('using_calls',-1),('outside_ns',2**64),
    ('sample_age_state','known'),('precise_termination_hotspot_known',True),('cpu_attribution','exclusive')])
def test_console_rejects_misleading_projection(field,value):
    summary=summarize(sparse_record());summary[field]=value
    assert not probe.valid_summary(summary)


def test_source_guard_rejects_grouped_or_unknown_input_and_restores_module_state(monkeypatch):
    original=probe.instrument.SOURCE_SHA256
    with pytest.raises(ValueError):probe.instrument_baseline('lib/templatesimplifier.cpp',b'grouped or unknown')
    assert probe.instrument.SOURCE_SHA256 is original
    raw=b'owned source';monkeypatch.setattr(probe,'BASELINE',{'lib/templatesimplifier.cpp':probe.digest(raw)})
    def fail(*args):raise ValueError('anchor_mismatch')
    monkeypatch.setattr(probe.instrument,'instrument',fail)
    with pytest.raises(ValueError):probe.instrument_baseline('lib/templatesimplifier.cpp',raw)
    assert probe.instrument.SOURCE_SHA256 is original


def test_receipt_binds_every_instrumentation_input_and_excludes_optimizer():
    receipt=probe.expected_receipt()
    assert receipt['source_sha256']['lib/templatesimplifier.cpp']=='61e6d1c8be0327fe8689c132b95ad519d95685e88d9766e8862e625b80e11d4f'
    assert receipt['grouping_applied'] is False and receipt['qualification_credit'] is False
    assert receipt['restored_source_sha256']==receipt['source_sha256']
    assert receipt['header_sha256']==probe.digest(probe.instrument.HEADER.read_bytes())
    recipe=build.recipe('sha256:'+'1'*64)
    assert 'python3 /opt/cpp_template_probe.py --source' in recipe
    assert 'specialization_groups' not in recipe
    assert 'COPY native_stage_counters /opt/native_stage_counters' in recipe


def test_old_binding_or_disabled_activation_rejected():
    from tests.test_cpp_phase_boundaries import binding
    value=binding();assert build.validate_binding(value,value['image'])==value
    value['activation']={'NICO_CPP_STAGE_COUNTERS':'0'}
    with pytest.raises(ValueError):build.validate_binding(value,value['image'])
    value=binding();value['schema']='nico.cpp-phase-binding.v1'
    with pytest.raises(ValueError):build.validate_binding(value,value['image'])


def test_owned_observed_summary_is_bound_and_sanitized(tmp_path,monkeypatch,capsys):
    from tests.test_cpp_phase_boundaries import binding
    from tests.test_fresh_cpp_phase_diagnostic import owned,observed
    from tests.test_cpp_project_static import execution
    request,data=owned(tmp_path,monkeypatch)
    data['records'][0]['execution']=execution(b'PRIVATE_SECRET\n'+sparse_record())
    summary=fresh.summarize(observed(data),request,binding())
    assert summary['records'][0]['subphases']['state']=='observed_prefix'
    assert summary['probe_activation_sha256']==build.digest(build.canonical(binding()['activation']))
    fresh.emit_summary(summary);raw=capsys.readouterr().out
    assert 'PRIVATE' not in raw and len(raw.encode())<fresh.CONSOLE_LIMIT
    assert json.loads(raw)==summary
    summary['records'][0]['subphases']['command']='PRIVATE'
    fresh.emit_summary(summary);assert json.loads(capsys.readouterr().out)['state']=='invalid'


def test_worst_width_projection_fits_existing_console_bound(capsys):
    # Sixteen context rows, with details only for two, does not lower execution population.
    summary=fresh.empty_summary('collected');summary.update(observed_contexts=577,
        request_sha256='a'*64,native_evidence_sha256='b'*64,source_population_sha256='c'*64,
        collection_duration_ms=540192,omitted_executed_records=561,boundary_binding_sha256='d'*64,
        diagnostic_image_sha256='e'*64,diagnostic_binary_sha256='f'*64,
        planned_probe_invocations_sha256='a'*64,probe_activation_sha256='b'*64)
    detailed=summarize(sparse_record())
    for k in probe.COUNT_FIELDS:detailed[k]=2**64-1
    detailed.update({'pass':10,'active_bucket':4,'transition_saturated':1,'thread_clock_status':1,'interval_kind':5})
    detailed['last_interval_deltas']={k:2**64-1 for k in probe.DELTA_FIELDS}
    for i in range(16):
        summary['records'].append(dict(context_index=i,exit_code=124,timed_out=True,output_truncated=False,
            duration_ms=90063,phases={v:{'state':'available','cpu_microseconds':540000000} for v in fresh.PHASES.values()},
            boundaries={'state':'observed','last_boundary':'template_end','precise_hotspot_known':False},
            subphases=detailed if i in (0,15) else probe.unknown_summary('omitted')))
    fresh.emit_summary(summary);raw=capsys.readouterr().out
    assert len(raw.encode())<fresh.CONSOLE_LIMIT
    assert json.loads(raw)['state']=='collected'


def test_projection_retains_two_failure_classes_without_changing_population():
    rows=[{'context_index':i,'boundaries':{'last_boundary':'template_begin'}} for i in range(13)]
    for i,name in ((10,'template_end'),(11,'tokens_simplified'),(12,'normal_checks_begin')):
        rows[i]['boundaries']['last_boundary']=name
    assert fresh._subphase_detail_indices(rows)=={0,12}
    assert len(rows)==13 and rows[11]['boundaries']['last_boundary']=='tokens_simplified'


def test_later_boundaries_require_exact_order_and_never_mean_success():
    from scripts import cpp_phase_boundaries as phase
    raw=b''
    for name in phase.BOUNDARIES:
        raw+=b'NICO_PHASE_V1 '+name.encode()+b'\n'
        value=phase.parse_markers(raw)
        assert value=={'state':'observed','last_boundary':name,'precise_hotspot_known':False}
    assert phase.parse_markers(raw+raw)['state']=='capped'
    assert phase.parse_markers(raw.replace(b'parsed_membership_end',b'normal_checks_end'))['state']=='invalid'


def test_truncated_timing_prefix_never_hides_missing_duplicate(tmp_path,monkeypatch):
    from tests.test_fresh_cpp_phase_diagnostic import owned,observed
    request,data=owned(tmp_path,monkeypatch)
    # A fully printed first timing remains unavailable if its suffix was lost.
    data['records'][0]['execution']['output_truncated']=True
    summary=fresh.summarize(observed(data),request)
    assert summary['state']=='collected'
    assert all(v=={'state':'unavailable'} for v in summary['records'][0]['phases'].values())


def test_shared_boundary_cap_across_translation_units(tmp_path,monkeypatch):
    import subprocess
    from scripts import cpp_phase_boundaries as phase
    raw=(b'#include "tokenize.h"\n    // using A = B;\n    while (simplifyUsing())\n        ;\n'
         b'        // Handle templates..\n            simplifyTemplates();\n        });\n')
    monkeypatch.setattr(phase,'PIN',build.digest(raw));changed=phase.overlay(raw)
    helper=changed[changed.index(b'#include <cstdio>'):changed.index(phase.END)]
    a=tmp_path/'a.cpp';b=tmp_path/'b.cpp';binary=tmp_path/'cap'
    a.write_bytes(helper+b'\nvoid other(); int main(){ for(int i=0;i<10;++i) { nicoPhaseBoundary("NICO_PHASE_V1 using_begin\\n"); other(); } }\n')
    b.write_text('void nicoPhaseBoundary(const char*); void other(){nicoPhaseBoundary("NICO_PHASE_V1 normal_checks_end\\n");}\n')
    subprocess.run(['g++','-std=c++11',str(a),str(b),'-o',str(binary)],check=True,capture_output=True,timeout=20)
    r=subprocess.run([str(binary)],capture_output=True,check=True,timeout=10)
    assert len(r.stderr.splitlines())==16
