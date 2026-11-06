"""Owned synthetic captures only; no scanner execution or retained findings."""
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml
from scripts import security_fresh_projection as p
from scripts import security_audit_gate as gate
from tests.test_security_audit_gate import _clean_evidence, _write
from tests.test_security_source_dispositions import synthetic, summary, independent_pair

CANARY = 'OWNED_PRIVATE_CANARY_NEVER_EXPORT'

@pytest.fixture
def capture_root(tmp_path, monkeypatch):
    monkeypatch.setenv('GITHUB_RUN_ID','123')
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT','1')
    monkeypatch.setenv('SECURITY_PROJECTION_PREPARE_OK','1')
    monkeypatch.setenv('SECURITY_PROJECTION_CAPTURE_OK','1')
    for tool in p.TOOLS:monkeypatch.setenv('SECURITY_PROJECTION_'+tool.upper()+'_FRESH','true')
    (tmp_path/'.github/workflows').mkdir(parents=True)
    (tmp_path/'.github/workflows/security-audit.yml').write_text('owned workflow')
    for args in (['init','-q'],['add','.'],['-c','user.name=Owned','-c','user.email=owned@example.invalid','commit','-qm','owned']):
        subprocess.run(['git',*args],cwd=tmp_path,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    monkeypatch.setattr(p.shutil,'which',lambda tool:None)
    return tmp_path


def complete(root, findings=None, semgrep=None):
    for tool in p.TOOLS:p.prepare(root,tool)
    _clean_evidence(root)
    findings=[] if findings is None else findings
    semgrep={'results':[],'errors':[],'version':'1.170.0'} if semgrep is None else semgrep
    _write(root,'gitleaks.json',findings)
    _write(root,'gitleaks-summary.json',summary(len(findings)))
    _write(root,'semgrep.json',semgrep)
    for tool in p.TOOLS:
        p.capture(root,tool,int(bool(findings)) if tool=='gitleaks' else 7)
        p.seal(root,tool)
    manifest=gate.build_manifest(root,repository='owned/project',run_id='123',require_sanitized_trufflehog=True)
    _write(root,'scanner-worker-artifact.json',manifest)
    return p.emit(root)


def records(raw):return [json.loads(line)for line in raw.splitlines()]

@pytest.mark.parametrize('count',[0,1,23,67,110])
def test_real_git_lifecycle_combined_bounds(capture_root,count):
    output=complete(capture_root,[synthetic(i)for i in range(count)],
        {'results':[],'errors':[{'level':'warn','type':CANARY,'message':CANARY}for _ in range(26)]})
    assert p.validate_console(output)
    assert len(output.splitlines())==count+17<=128
    assert max(map(len,output.splitlines(keepends=True)))<=512
    assert len(output)<=65536 and CANARY.encode()not in output
    rows=records(output)
    assert rows[0]['finding_count']==count
    assert next(r for r in rows if r.get('record')=='semgrep_categories')['unclassified_entries']==26
    assert next(r for r in rows if r.get('record')=='execution' and r['tool']=='semgrep')['actual_exit']==7


def test_exact_matches_and_same_fingerprint_distinct_columns(capture_root,monkeypatch):
    findings=[synthetic(i)for i in range(23)]
    monkeypatch.setattr(p.dispositions,'_approved_bindings',lambda:frozenset(independent_pair(f)for f in findings))
    output=complete(capture_root,findings)
    assert p.validate_console(output)
    assert records(output)[2]['matched_occurrences']==23
    assert records(output)[0]['blocking_count']==0

@pytest.mark.parametrize('paths,expected',[(None,'unavailable'),({},'unavailable'),({'scanned':[]},0),
    ({'scanned':[CANARY,CANARY]},2),({'scanned':[False]},'unavailable'),({'scanned':CANARY},'unavailable')])
def test_reported_scanned_entries_not_unique_or_complete_coverage(capture_root,paths,expected):
    output=complete(capture_root,semgrep={'results':[],'errors':[],'paths':paths,'skipped_rules':[CANARY]})
    row=next(r for r in records(output)if r.get('record')=='semgrep_coverage')
    assert row['scanned']==expected and row['targets']=='unavailable' and row['skipped']=='unavailable'
    assert CANARY.encode()not in output and p.validate_console(output)

@pytest.mark.parametrize('tool',p.TOOLS)
def test_missing_original_report_fallback_is_not_fresh(capture_root,tool):
    p.prepare(capture_root,tool)
    p.capture(capture_root,tool,0)
    _write(capture_root,p.REPORTS[tool],[] if tool=='gitleaks'else {'results':[],'errors':[]})
    _write(capture_root,'gitleaks-summary.json',summary(0))
    with pytest.raises(p.Invalid,match='report'):p.seal(capture_root,tool)
    assert not (capture_root/p.CONTEXTS[tool]).exists()

@pytest.mark.parametrize('env',['SECURITY_PROJECTION_PREPARE_OK','SECURITY_PROJECTION_CAPTURE_OK'])
def test_missing_lifecycle_flags(capture_root,monkeypatch,env):
    complete(capture_root)
    monkeypatch.setenv(env,'0')
    with pytest.raises(p.Invalid,match='freshness'):p.seal(capture_root,'gitleaks')
    monkeypatch.setenv('SECURITY_PROJECTION_GITLEAKS_FRESH','')
    with pytest.raises(p.Invalid,match='freshness'):p.emit(capture_root)

@pytest.mark.parametrize('file',['gitleaks.json','gitleaks-summary.json','semgrep.json','.github/workflows/security-audit.yml'])
def test_postseal_mutation_rejected(capture_root,file):
    complete(capture_root)
    (capture_root/file).write_text(CANARY)
    with pytest.raises(Exception):p.emit(capture_root)


def test_changed_run_and_resealed_context_rejected(capture_root,monkeypatch):
    complete(capture_root)
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT','2')
    with pytest.raises(p.Invalid,match='binding'):p.emit(capture_root)
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT','1')
    with pytest.raises(p.Invalid,match='context'):p.seal(capture_root,'gitleaks')
    assert not (capture_root/p.CONTEXTS['gitleaks']).exists()


def test_tracked_output_not_removed(capture_root):
    _write(capture_root,'gitleaks.json',[])
    subprocess.run(['git','add','gitleaks.json'],cwd=capture_root,check=True)
    with pytest.raises(p.Invalid,match='tracked_output'):p.prepare(capture_root,'gitleaks')
    assert (capture_root/'gitleaks.json').read_text()=='[]'

@pytest.mark.parametrize('raw',[b'',b'{',b'{"results":[],"results":[],"errors":[]}',b'{"results":[],"errors":[],"x":NaN}',
    b'['*2000+b']'*2000,b'x'*(4*1024*1024+1)],ids=['empty','syntax','duplicate','nonfinite','depth','oversized'])
def test_invalid_inputs_fixed_output(capture_root,raw,capfd):
    complete(capture_root)
    (capture_root/'semgrep.json').write_bytes(raw)
    assert p.main(['emit','--root',str(capture_root)])==1
    out,err=capfd.readouterr()
    assert not err and len(out.encode())<=512
    assert json.loads(out)['state']=='invalid' and CANARY not in out

@pytest.mark.parametrize('kind,count',[('errors',2049),('results',10001)])
def test_semgrep_population_cap(capture_root,kind,count):
    value={'results':[],'errors':[]};value[kind]=[{}]*count
    with pytest.raises(p.Invalid,match='semgrep'):complete(capture_root,semgrep=value)


def test_nonfatal_fatal_and_malformed_entries_preserve_gate(capture_root):
    output=complete(capture_root,semgrep={'results':[{},False],'errors':[{'level':'fatal','message':CANARY},None,{}, {'level':False}]})
    rows=records(output);assert rows[0]['gate']=='blocked'
    counts=next(r for r in rows if r.get('record')=='semgrep_counts')
    assert counts['malformed_diagnostics']==1 and counts['malformed_results']==1
    assert CANARY.encode()not in output


def test_transport_truncation_reorder_and_counter_mutation(capture_root):
    raw=complete(capture_root,[synthetic(0),synthetic(1)])
    assert not p.validate_console(raw[:-1])
    assert not p.validate_console(b'\n'.join(raw.splitlines()[:-1])+b'\n')
    rows=records(raw)[:-1];rows[3],rows[4]=rows[4],rows[3]
    assert not p.validate_console(p.frame(rows))
    rows=records(raw)[:-1];rows[0]['finding_count']=True
    assert not p.validate_console(p.frame(rows))
    rows=records(raw)[:-1];rows[11]['index']=0
    assert not p.validate_console(p.frame(rows))


def test_short_writes_and_broken_output(monkeypatch):
    chunks=[]
    def short(fd,data):chunks.append(data[:2]);return min(2,len(data))
    monkeypatch.setattr(p.os,'write',short)
    assert p.write_output(b'abcdef') and b''.join(chunks)==b'abcdef'
    monkeypatch.setattr(p.os,'write',lambda *args:0)
    assert not p.write_output(b'x')
    def broken(*args):raise OSError(CANARY)
    monkeypatch.setattr(p.os,'write',broken)
    assert not p.write_output(b'x')


def test_cli_no_dynamic_errors(capfd):
    assert p.main(['emit','--'+CANARY])==1
    out,err=capfd.readouterr()
    assert not err and CANARY not in out and json.loads(out)['reason']=='arguments'


def test_workflow_preserves_scanner_flags_and_always_enforcement():
    workflow=yaml.safe_load((Path(__file__).parents[1]/'.github/workflows/security-audit.yml').read_text())
    steps=next(job['steps']for job in workflow['jobs'].values()if any(s.get('name')=='Collect Semgrep evidence'for s in job['steps']))
    for tool,name in [('semgrep','Collect Semgrep evidence'),('gitleaks','Collect gitleaks git-history evidence')]:
        step=next(s for s in steps if s.get('name')==name);run=step['run']
        assert run.index(' prepare ')<run.index('status=$?')<run.index(' capture ')<run.index("python - ")<run.index(' seal ')
        assert ' '.join(p.INVOCATIONS[tool])+' >/dev/null 2>' in run
        assert run.count(' --kill-after=2s 30s ')==3
        assert "echo 'sealed=true'"in run
    projection=next(s for s in steps if s.get('name')=='Project bounded fresh security diagnostics')
    assert projection['if']=='always()'
    for step in steps:
        if step.get('name')in ('Build fail-closed scanner manifest','Upload audit evidence before enforcement','Require complete clean security evidence'):assert step['if']=='always()'

@pytest.mark.parametrize('raw',[b'',b'{',b'{"results":[],"results":[],"errors":[]}',b'{"results":[],"errors":[],"x":NaN}', b'['*2000+b']'*2000],ids=['empty','syntax','duplicate','nonfinite','depth'])
def test_decoder_rejects_invalid_capture_not_only_hash_mismatch(raw):
    with pytest.raises(Exception):p.semgrep_projection(raw,{})

@pytest.mark.parametrize('kind,count',[('errors',2048),('results',10000)])
def test_semgrep_exact_population_boundary(capture_root,kind,count):
    value={'results':[],'errors':[]};value[kind]=[{}]*count
    assert p.validate_console(complete(capture_root,semgrep=value))

@pytest.mark.parametrize('count',[111])
def test_gitleaks_capture_limit_is_not_output_truncation(capture_root,count):
    with pytest.raises(p.Invalid,match='gitleaks_validation'):
        complete(capture_root,[synthetic(i)for i in range(count)])

@pytest.mark.parametrize('field,record',[('unclassified_entries','semgrep_categories'),('reported_entries','semgrep_groups')])
def test_boolean_transport_counts_rejected(capture_root,field,record):
    raw=complete(capture_root,semgrep={'results':[],'errors':[{}]})
    rows=records(raw)[:-1]
    next(row for row in rows if row.get('record')==record)[field]=True
    assert not p.validate_console(p.frame(rows))


def test_read_bounds_and_symlinks(capture_root):
    path=capture_root/'owned.json';path.write_bytes(b'x'*(4*1024*1024))
    assert len(p.common.read(path))==4*1024*1024
    path.write_bytes(b'x'*(4*1024*1024+1))
    with pytest.raises(Exception):p.common.read(path)
    link=capture_root/'link.json';link.symlink_to(path)
    with pytest.raises(Exception):p.common.read(link)


def test_ignored_fields_canaries_and_nonfinite_capture(capture_root):
    finding=synthetic(1)
    finding.update(Message=CANARY,Author=CANARY,Description=CANARY,Email=CANARY,Link=CANARY,Tags=[CANARY])
    output=complete(capture_root,[finding],{'results':[{'check_id':CANARY,'path':CANARY,'extra':{'message':CANARY,'lines':CANARY}}],
        'errors':[{'level':'warn','type':CANARY,'message':CANARY,'location':{'path':CANARY}}],'paths':{'scanned':[CANARY]}})
    assert CANARY.encode()not in output and p.validate_console(output)
    finding['Entropy']=float('nan')
    with pytest.raises(p.Invalid,match='gitleaks_validation'):complete(capture_root,[finding])
