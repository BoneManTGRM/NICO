"""Fail-closed diagnostic identity, parser, runtime and CI wiring controls."""
from pathlib import Path
import copy
import hashlib
import json
import subprocess
import pytest
from scripts import cpp_phase_boundaries as phase
from scripts import build_cpp_phase_boundaries as build
from scripts import fresh_cpp_phase_diagnostic as fresh


def binding():
    original='sha256:'+'1'*64;image='sha256:'+'2'*64
    return dict(schema='nico.cpp-phase-binding.v1',original_image=original,image=image,
        upstream=build.UPSTREAM,recipe_sha256=build.digest(build.recipe(original).encode()),
        overlay=build.expected_overlay(),files={k:'3'*64 for k in build.FILES},
        diagnostic_binary_sha256='4'*64,diagnostic_binary_path=build.BINARY,qualification_credit=False)


def test_overlay_rejects_wrong_source_and_restores_owned_bytes(monkeypatch):
    raw=(b'#include "tokenize.h"\n    // using A = B;\n    while (simplifyUsing())\n        ;\n'
         b'        // Handle templates..\n            simplifyTemplates();\n        });\n')
    with pytest.raises(ValueError):phase.overlay(raw)
    monkeypatch.setattr(phase,'PIN',build.digest(raw))
    updated=phase.overlay(raw)
    assert phase.strip(updated)==raw
    with pytest.raises(ValueError):phase.overlay(updated)
    with pytest.raises(ValueError):phase.overlay(raw+b'\n')
    assert updated.count(b'nicoPhaseBoundary("NICO_PHASE_V1 ')==4


def test_process_wide_cap_even_with_concurrent_threads(tmp_path,monkeypatch):
    raw=(b'#include "tokenize.h"\n    // using A = B;\n    while (simplifyUsing())\n        ;\n'
         b'        // Handle templates..\n            simplifyTemplates();\n        });\n')
    monkeypatch.setattr(phase,'PIN',build.digest(raw));changed=phase.overlay(raw)
    helper=changed[changed.index(b'#include <cstdio>'):changed.index(phase.END)]
    p=tmp_path/'cap.cpp';binary=tmp_path/'cap'
    p.write_bytes(helper+b'\n#include <thread>\n#include <vector>\nint main() { std::vector<std::thread> ts; for(int i=0;i<8;++i) ts.emplace_back([] { for(int j=0;j<100;++j) nicoPhaseBoundary("NICO_PHASE_V1 using_begin\\n"); }); for(auto& t:ts) t.join(); }\n')
    subprocess.run(['g++','-std=c++11','-pthread',str(p),'-o',str(binary)],check=True,capture_output=True,timeout=20)
    result=subprocess.run([str(binary)],capture_output=True,timeout=10,check=True)
    assert result.stderr.splitlines()==[b'NICO_PHASE_V1 using_begin']*16


@pytest.mark.parametrize('raw,state,last',[
    (b'', 'unavailable',None), (b'SECRET\n','unavailable',None),
    (b'NICO_PHASE_V1 using_begin\n','observed','using_begin'),
    (b'NICO_PHASE_V1 using_begin\nNICO_PHASE_V1 using_end\n','observed','using_end'),
    (b'NICO_PHASE_V1 using_end\n','invalid',None),
    (b'NICO_PHASE_V1 using_begin','invalid',None),
    (b'NICO_PHASE_V1 using_begin\nNICO_PHASE_V1 using_begin\n','invalid',None),
    (b'NICO_PHASE_V1 secret_path\n','invalid',None),
    (b'NICO_PHASE_V1 using_begin\n'*16,'capped',None),
    (b'x'*65537,'unavailable',None),
])
def test_marker_evidence_unknown_on_bad_or_incomplete_input(raw,state,last):
    assert phase.parse_markers(raw)=={'state':state,'last_boundary':last,'precise_hotspot_known':False}


def test_full_marker_cycle_and_second_cycle_unknown():
    raw=b''.join(b'NICO_PHASE_V1 '+s+b'\n' for s in [b'using_begin',b'using_end',b'template_begin',b'template_end'])
    assert phase.parse_markers(raw)['last_boundary']=='template_end'
    assert phase.parse_markers(raw+raw)['state']=='invalid'


@pytest.mark.parametrize('field', ['schema','original_image','image','upstream','recipe_sha256','overlay','files','diagnostic_binary_sha256','diagnostic_binary_path','qualification_credit'])
def test_binding_mutations_rejected(field):
    value=binding();assert build.validate_binding(value,value['image'])==value
    value[field]='wrong'
    with pytest.raises((ValueError,TypeError)):build.validate_binding(value,'sha256:'+'2'*64)


def test_recipe_preserves_original_analyzer_and_bound_build():
    recipe=build.recipe(binding()['original_image'])
    assert 'FROM nico-phase-base:'+'1'*64 in recipe
    assert '# Original image identity: sha256:'+'1'*64 in recipe
    assert 'timeout 180s make' in recipe and '-j2 MATCHCOMPILER=yes' in recipe
    assert 'cp /opt/phase-tool-src/cppcheck /usr/local/bin/cppcheck-phase-boundaries' in recipe
    assert 'cp /opt/phase-tool-src/cppcheck /usr/local/bin/cppcheck\n' not in recipe
    for expected in ('cmp /opt/phase-repair.json','cmp /opt/phase-grammar.json','cmp /opt/phase-header.json','USER 1000:1000'):
        assert expected in recipe


def test_runtime_checks_hashes_before_execution_and_redirects_only_analyzer(monkeypatch):
    value=binding();calls=[];seen=[]
    prefix="\ndef _run(argv, stem, deadline, environment):\n    calls.append((argv,stem,deadline,environment)); return 'owned'\ndef run_project_static(): pass\n"
    monkeypatch.setattr(fresh,'PROGRAM',prefix+'\nrun_project_static()\n')
    def read(path,limit):seen.append((path,limit));return path.encode()
    value['files']={k:build.digest(v.encode()) for k,v in build.FILES.items()}
    value['diagnostic_binary_sha256']=build.digest(build.BINARY.encode())
    ns={'calls':calls,'_regular_bytes':read,'_digest':build.digest}
    exec(fresh.diagnostic_program(value),ns)
    assert {p for p,_ in seen}==set(build.FILES.values())|{build.BINARY}
    assert all(limit==67108864 for _,limit in seen)
    env={'PATH':'owned'}
    ns['_run'](['/usr/local/bin/cppcheck','--project=owned'],'stem',123,env)
    assert calls[-1]==([build.BINARY,'--project=owned','--showtime=file'],'stem',123,env)
    ns['_run'](['/usr/local/bin/cppcheck','--version'],'version',5,env)
    assert calls[-1][0]==[build.BINARY,'--version']
    value['files']['production_binary']='f'*64
    with pytest.raises(ValueError,match='phase_runtime_tool_identity'):exec(fresh.diagnostic_program(value),ns)


def test_summary_binds_actual_invocations_and_console_rejects_raw_fields(tmp_path,monkeypatch,capsys):
    from test_fresh_cpp_phase_diagnostic import owned,observed
    request,evidence=owned(tmp_path,monkeypatch)
    summary=fresh.summarize(observed(evidence),request,binding())
    assert summary['state']=='collected'
    assert summary['boundary_binding_sha256']==build.digest(build.canonical(binding()))
    assert summary['planned_probe_invocations_sha256']==build.digest(build.canonical([
        [build.BINARY,*c['analyzer_invocation'][1:],'--showtime=file'] for c in request['contexts']]))
    fresh.emit_summary(summary);assert json.loads(capsys.readouterr().out)==summary
    summary['records'][0]['boundaries']['path']='SECRET'
    fresh.emit_summary(summary);assert json.loads(capsys.readouterr().out)['state']=='invalid'


def test_workflow_preserves_production_controls_then_binds_fresh_probe():
    import yaml
    root=Path(__file__).resolve().parents[1]
    w=yaml.safe_load((root/'.github/workflows/native-timeout-diagnostic.yml').read_text())
    job=w['jobs']['isolated-diagnostic'];steps=job['steps']
    build_step=next(s for s in steps if s.get('name')=='Build and bind the diagnostic-only phase boundary image')
    assert 'timeout --kill-after=10s 300s docker build --network=none' in build_step['run']
    assert '--original-image "$(cat full-project-image-id.txt)"' in build_step['run']
    assert '--recipe toolchain/phase-boundaries/Dockerfile' in build_step['run']
    measure=next(s for s in steps if s.get('name')=='Measure fresh source-bound primary phases without qualification credit')
    assert '--image "$(cat phase-image-id.txt)" --boundary-binding phase-image-binding/binding.json' in measure['run']
    for s in steps:
        if any(term in s.get('run','') for term in ['scripts.qualify_cppcheck_worker_control','scripts.qualify_cpp_full_project_integration','scripts.qualify_cpp_project_generated_context']):
            assert '--image "$(cat full-project-image-id.txt)"' in s['run']
            assert steps.index(s)<steps.index(build_step)
    assert job['env']['NICO_TEST_DATABASE_URL']=='postgresql://nico:nico@127.0.0.1:5432/nico'
    assert w['on']['pull_request']['types']==['synchronize']
    assert '.github/workflows/native-timeout-diagnostic.yml' in w['on']['pull_request']['paths']
    assert 'tests/test_cpp_phase_boundaries.py' in next(s['run'] for s in steps if s.get('name')=='Verify diagnostic contracts')


@pytest.mark.parametrize('fault',[None,'layers','production','overlay','recipe'])
def test_capture_requires_derived_image_unchanged_tools_and_reviewed_recipe(tmp_path,monkeypatch,fault):
    from types import SimpleNamespace
    value=binding();original=value['original_image'];image=value['image']
    path=tmp_path/'Dockerfile';path.write_text(build.recipe(original)+ ('# altered' if fault=='recipe' else ''))
    before={k:('owned '+k).encode() for k in build.FILES}
    after={**before,'diagnostic_binary':b'owned instrumented binary','overlay':build.canonical(build.expected_overlay())}
    if fault=='production':after['production_binary']=b'changed'
    if fault=='overlay':after['overlay']=b'{}'
    def run(argv,**kwargs):
        layers=['sha256:'+'a'*64]
        if argv[-1]==image:layers=([ 'sha256:'+'b'*64] if fault=='layers' else layers)+['sha256:'+'c'*64]
        return SimpleNamespace(stdout=json.dumps([{'Id':argv[-1],'RootFS':{'Layers':layers}}]).encode())
    monkeypatch.setattr(build.subprocess,'run',run)
    monkeypatch.setattr(build,'capture_files',lambda identity,*a:before if identity==original else after)
    if fault:
        with pytest.raises(ValueError):build.capture(original,image,tmp_path/'output',path)
    else:
        result=build.capture(original,image,tmp_path/'output',path)
        assert result['files']=={k:build.digest(v) for k,v in before.items()}
        assert build.validate_binding(result,image)==result


def test_failed_capture_copy_always_cleans_owned_container(tmp_path,monkeypatch):
    from scripts.native_stage_counters import build as old_build
    calls=[];clean=[]
    def run(argv,**kwargs):
        calls.append(argv)
        if argv[:2]==['docker','cp']:raise subprocess.CalledProcessError(1,argv)
    monkeypatch.setattr(build.subprocess,'run',run)
    monkeypatch.setattr(old_build,'cleanup_capture_container',lambda name,owner:clean.append((name,owner)))
    with pytest.raises(subprocess.CalledProcessError):build.capture_files('sha256:'+'1'*64,{'owned':'/fixed'},tmp_path)
    assert len(clean)==1 and clean[0][0]==calls[0][3]
    assert 'nico.stage.capture-owner='+clean[0][1] in calls[0]
    assert '--network=none' in calls[0] and '--read-only' in calls[0]


@pytest.mark.parametrize('fault',[None,'head','dirty'])
def test_prepare_checks_upstream_before_copying_new_context(tmp_path,monkeypatch,fault):
    from types import SimpleNamespace
    source=tmp_path/'source';source.mkdir();(source/'owned.txt').write_text('owned')
    def run(argv,**kwargs):
        if argv[:2]==['docker','tag']:return SimpleNamespace(stdout=b'')
        if argv[:3]==['docker','image','inspect']:return SimpleNamespace(stdout=json.dumps([{'Id':'sha256:'+'1'*64}]).encode())
        if 'rev-parse' in argv:return SimpleNamespace(stdout=(('wrong' if fault=='head' else build.UPSTREAM)+'\n').encode())
        return SimpleNamespace(stdout=b' M owned.txt\n' if fault=='dirty' else b'')
    monkeypatch.setattr(build.subprocess,'run',run)
    context=tmp_path/'context';image='sha256:'+'1'*64
    if fault:
        with pytest.raises(ValueError):build.prepare(context,source,image)
        assert not context.exists()
    else:
        receipt=build.prepare(context,source,image)
        assert receipt['recipe_sha256']==build.digest((context/'Dockerfile').read_bytes())
        assert (context/'cpp_phase_boundaries.py').read_bytes()==Path(phase.__file__).read_bytes()
        with pytest.raises(ValueError):build.prepare(context,source,image)
