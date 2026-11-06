"""Synthetic canaries only; no scanner execution or external calls."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from scripts import security_identity_console as identity
from scripts import security_audit_gate as gate

CANARY='PRIVATE_CANARY_never_print'

def is_invalid(raw):
    assert len(raw) <= 512 and raw.endswith(b'\n') and len(raw.splitlines()) == 1
    value = json.loads(raw)
    assert set(value) == {'schema', 'state', 'phase', 'reason'}
    assert value['schema'] == 'nico.security-identity.v1' and value['state'] == 'invalid'
    assert value['phase'] in identity.PHASES and value['reason'] in identity.REASONS
    assert not identity.validate_console(raw)
    return True



def finding(index=0):
    commit='a'*40;path=f'src/{CANARY}{index}.txt';rule='generic-api-key'
    return {'Commit':commit,'File':path,'RuleID':rule,'StartLine':index+1,'EndLine':index+1,
        'StartColumn':1,'EndColumn':9,'Fingerprint':f'{commit}:{path}:{rule}:{index+1}',
        'Match':CANARY+' REDACTED','Secret':'REDACTED','Author':CANARY,'Link':CANARY,'SymlinkFile':'','Tags':[],'Entropy':1.5}


@pytest.fixture
def owned(tmp_path,monkeypatch):
    monkeypatch.setenv('SECURITY_IDENTITY_PREPARE_OK','1')
    monkeypatch.setenv('SECURITY_IDENTITY_FRESH_CAPTURE','true')
    monkeypatch.setenv('GITHUB_RUN_ID','17')
    def bindings(root,nonce):
        return {k:nonce if k=='nonce'else identity.digest(b'17')if k=='run'else identity.digest(k.encode())for k in identity.BINDINGS}
    monkeypatch.setattr(identity,'capture_bindings',bindings)
    monkeypatch.setattr(identity,'git_bytes',lambda root,args:b'')
    def build(data=None):
        data=[finding()]if data is None else data
        identity.prepare(tmp_path)
        (tmp_path/identity.REPORT).write_bytes(identity.canonical(data))
        summary={'scanner':'gitleaks','status':'completed','finding_count':len(data),'artifact_present':True,'history_depth':'full','exit_code':1 if data else 0}
        (tmp_path/identity.SUMMARY).write_bytes(identity.canonical(summary))
        identity.seal(tmp_path)
        manifest=gate.build_manifest(tmp_path,repository='owned',run_id='17',require_sanitized_trufflehog=True)
        (tmp_path/identity.MANIFEST).write_bytes(identity.canonical(manifest))
        return manifest
    build()
    return tmp_path,build


def emit_cli(root,capfd):
    status=identity.main(['emit','--root',str(root)])
    captured=capfd.readouterr()
    assert CANARY not in captured.out+captured.err
    assert captured.err==''
    return status,captured.out.encode()


def test_complete_identity_console_no_raw_fields_and_exact_hashes(owned,capfd):
    root,_=owned;before={p.name:p.read_bytes()for p in root.iterdir()}
    status,raw=emit_cli(root,capfd)
    assert status==0 and identity.validate_console(raw)
    rows=[json.loads(x)for x in raw.splitlines()]
    row=next(x for x in rows if x.get('record')=='finding');f=finding()
    shape=[f[k]for k in ('Commit','File','RuleID','StartLine','EndLine','StartColumn','EndColumn','Fingerprint')]+[identity.digest(f['Match'].encode()),'REDACTED','verified_absent']
    assert row['fingerprint_sha256']==identity.digest(f['Fingerprint'].encode())
    assert row['shape_hash']==identity.digest(identity.canonical(shape))
    assert before=={p.name:p.read_bytes()for p in root.iterdir()}
    assert all(len(line)+1<=512 for line in raw.splitlines())


@pytest.mark.parametrize('which',[identity.REPORT,identity.SUMMARY,identity.MANIFEST,identity.CONTEXT])
def test_duplicate_keys_and_tampering_never_print_input(owned,capfd,which):
    root,_=owned;(root/which).write_text('{"canary":"'+CANARY+'","canary":1}')
    status,raw=emit_cli(root,capfd);assert status==1 and is_invalid(raw)


@pytest.mark.parametrize('mutation',[
    lambda f:f.update(Secret=CANARY),lambda f:f.update(StartLine=True),lambda f:f.update(EndColumn=0),
    lambda f:f.update(Verified=False),lambda f:f.update(Verified=None),lambda f:f.update(Unknown=CANARY),
    lambda f:f.update(Commit='b'*40),lambda f:f.update(File='../'+CANARY),lambda f:f.update(Entropy=True),
    lambda f:f.update(Match=CANARY),lambda f:f.update(Tags=[False]),lambda f:f.update(Fingerprint=CANARY),
])
def test_invalid_finding_shape_rejected(owned,mutation):
    root,_=owned;f=finding();mutation(f)
    with pytest.raises((ValueError,TypeError,UnicodeError)):
        identity.parse_findings(identity.canonical([f]),(root/identity.SUMMARY).read_bytes())


def test_duplicate_occurrence_and_fingerprint_rejected(owned):
    root,_=owned;summary=json.loads((root/identity.SUMMARY).read_bytes());summary['finding_count']=2
    with pytest.raises(ValueError):identity.parse_findings(identity.canonical([finding(),finding()]),identity.canonical(summary))


@pytest.mark.parametrize('mutation',[
    lambda m:m['tools']['gitleaks'].update(finding_count=True),
    lambda m:m['tools']['gitleaks'].update(blocking=0),
    lambda m:m['tools']['gitleaks'].update(triage=[]),
    lambda m:m['tools']['gitleaks']['triage'][0].update(disposition=CANARY),
    lambda m:m['tools']['gitleaks']['triage'][0].update(line=True),
    lambda m:m['tools']['gitleaks'].update(artifact_hash='0'*64),
    lambda m:m['tools']['gitleaks'].update(summary_artifact_hash='0'*64),
    lambda m:m['security_gate'].update(status='passed'),
    lambda m:m['security_gate'].update(untriaged_secret_findings_allowed=0),
    lambda m:m.update(run_id='18'),lambda m:m.update(client_delivery_allowed=True),
])
def test_manifest_mismatch_and_policy_changes_fail_closed(owned,capfd,mutation):
    root,_=owned;m=json.loads((root/identity.MANIFEST).read_bytes());mutation(m)
    (root/identity.MANIFEST).write_bytes(identity.canonical(m));status,raw=emit_cli(root,capfd)
    assert status==1 and is_invalid(raw)


def test_exact_record_cap_and_one_over(owned,capfd):
    root,build=owned;n=identity.MAX_RECORDS-len(identity.BINDINGS)-3
    build([finding(i)for i in range(n)]);status,raw=emit_cli(root,capfd)
    assert status==0 and len(raw.splitlines())==128 and identity.validate_console(raw)
    with pytest.raises(ValueError):build([finding(i)for i in range(n+1)])
    assert not (root/identity.CONTEXT).exists()


def test_oversized_input_no_disclosure(owned,capfd):
    root,_=owned;(root/identity.MANIFEST).write_bytes(b'X'*(identity.LIMIT+1))
    status,raw=emit_cli(root,capfd);assert status==1 and is_invalid(raw)


def test_console_truncation_reorder_duplicate_trailer_fail(owned):
    root,_=owned;raw=identity.emit(root);lines=raw.splitlines(keepends=True)
    assert identity.validate_console(raw)
    for broken in [raw[:-1],b''.join(lines[:-1]),b''.join(lines[1:]),b''.join([lines[1],lines[0],*lines[2:]]),raw+lines[-1]]:
        assert not identity.validate_console(broken)


def test_prepare_removes_stale_context_before_later_failure(owned,monkeypatch):
    root,_=owned;(root/identity.REPORT).unlink();(root/identity.REPORT).mkdir()
    with pytest.raises(identity.DiagnosticFailure):identity.prepare(root)
    assert not (root/identity.CONTEXT).exists()


def test_prepare_refuses_tracked_report_without_deleting_it(owned,monkeypatch):
    root,_=owned;prior=(root/identity.REPORT).read_bytes()
    monkeypatch.setattr(identity,'git_bytes',lambda root,args:b''if identity.CONTEXT in args else b'gitleaks.json\0')
    with pytest.raises(ValueError):identity.prepare(root)
    assert (root/identity.REPORT).read_bytes()==prior and not (root/identity.CONTEXT).exists()


def test_reseal_rejects_and_invalidates_old_seal(owned):
    root,_=owned
    with pytest.raises(ValueError):identity.seal(root)
    assert not (root/identity.CONTEXT).exists()


def test_symlink_input_refused_without_reading_target(owned,capfd,tmp_path_factory):
    root,_=owned;target=tmp_path_factory.mktemp('outside')/'private';target.write_text(CANARY)
    (root/identity.MANIFEST).unlink();(root/identity.MANIFEST).symlink_to(target)
    status,raw=emit_cli(root,capfd);assert status==1 and is_invalid(raw)
    assert target.read_text()==CANARY


def test_invalid_cli_never_echoes_values(capfd):
    assert identity.main(['emit','--'+CANARY,CANARY])==1
    captured=capfd.readouterr();assert is_invalid(captured.out.encode()) and captured.err==''


def test_context_binding_change_rejected(owned,monkeypatch,capfd):
    root,_=owned;old=identity.capture_bindings
    def changed(root,nonce):
        data=old(root,nonce);data['attempt']='0'*64;return data
    monkeypatch.setattr(identity,'capture_bindings',changed)
    status,raw=emit_cli(root,capfd);assert status==1 and is_invalid(raw)


def test_same_fingerprint_distinct_columns_remain_two_occurrences(owned,capfd):
    root,build=owned;first=finding();second=deepcopy(first)
    second.update(StartColumn=11,EndColumn=19)
    build([first,second]);status,raw=emit_cli(root,capfd)
    assert status==0 and identity.validate_console(raw)
    rows=[json.loads(line)for line in raw.splitlines()]
    findings=[r for r in rows if r.get('record')=='finding']
    assert len(findings)==2 and findings[0]['fingerprint_sha256']==findings[1]['fingerprint_sha256']
    assert findings[0]['shape_hash']!=findings[1]['shape_hash']


@pytest.mark.parametrize('raw',[b'['*2000+b'0'+b']'*2000,b'{"x":NaN}',b'{"x":Infinity}'])
def test_deep_and_nonfinite_input_is_fixed_invalid(owned,capfd,raw):
    root,_=owned;(root/identity.MANIFEST).write_bytes(raw)
    status,output=emit_cli(root,capfd);assert status==1 and is_invalid(output)


def test_tool_fifo_rejected_without_blocking(tmp_path):
    import os
    path=tmp_path/'fifo';os.mkfifo(path)
    with pytest.raises(ValueError):identity.tool_digest(path)


def test_git_capture_overflow_kills_bounded_owned_child(tmp_path,monkeypatch):
    import subprocess,sys
    real=subprocess.Popen;children=[]
    def owned_child(*args,**kwargs):
        p=real([sys.executable,'-c','import os; os.write(1,b"x"*8192)'],stdout=kwargs['stdout'],stderr=kwargs['stderr'])
        children.append(p);return p
    monkeypatch.setattr(identity.subprocess,'Popen',owned_child);monkeypatch.setattr(identity,'LIMIT',1024)
    with pytest.raises(ValueError):identity.git_bytes(tmp_path,['owned'])
    assert children[0].poll()is not None


def test_real_owned_git_prepare_seal_emit_lifecycle(tmp_path,monkeypatch):
    import os,subprocess
    def git(*args):
        r=subprocess.run(['git','-c','core.hooksPath=/dev/null','-c','user.name=Owned','-c','user.email=owned@example.invalid',*args],cwd=tmp_path,capture_output=True,timeout=10)
        assert r.returncode==0
        return r.stdout.strip()
    git('init','-q');(tmp_path/'tracked.txt').write_text('owned\n');git('add','tracked.txt');git('commit','-qm','owned')
    head=git('rev-parse','HEAD').decode();tool=tmp_path/'bin';tool.mkdir();binary=tool/'gitleaks';binary.write_bytes(b'owned binary identity only');binary.chmod(0o700)
    (tmp_path/'.gitleaks.toml').write_text('owned config bytes')
    (tmp_path/'.github/workflows').mkdir(parents=True);(tmp_path/'.github/workflows/security-audit.yml').write_text('owned workflow bytes')
    monkeypatch.setenv('PATH',str(tool)+os.pathsep+os.environ['PATH'])
    monkeypatch.setenv('SECURITY_IDENTITY_PREPARE_OK','1')
    monkeypatch.setenv('SECURITY_IDENTITY_FRESH_CAPTURE','true')
    monkeypatch.setenv('GITHUB_RUN_ID','17');monkeypatch.setenv('GITHUB_RUN_ATTEMPT','2')
    monkeypatch.setenv('SECURITY_IDENTITY_PR_HEAD',head);monkeypatch.setenv('SECURITY_IDENTITY_BASE',head)
    identity.prepare(tmp_path)
    report=[finding()];(tmp_path/identity.REPORT).write_bytes(identity.canonical(report))
    summary={'scanner':'gitleaks','status':'completed','finding_count':1,'artifact_present':True,'history_depth':'full','exit_code':1}
    (tmp_path/identity.SUMMARY).write_bytes(identity.canonical(summary));identity.seal(tmp_path)
    m=gate.build_manifest(tmp_path,run_id='17',require_sanitized_trufflehog=True)
    (tmp_path/identity.MANIFEST).write_bytes(identity.canonical(m));output=identity.emit(tmp_path)
    assert identity.validate_console(output)
    context=identity.context_read(tmp_path)
    for key in ('head','tree','pr_head','base','tool','run','attempt','helper','workflow','config','refset'):
        assert identity.sha(context['bindings'][key]),key


@pytest.mark.parametrize('failure',[False,True])
def test_short_or_broken_output_never_claims_success(owned,monkeypatch,failure):
    root,_=owned;parts=[];calls=[]
    def write(fd,raw):
        calls.append(fd)
        if failure and len(calls)==2:raise BrokenPipeError(CANARY)
        part=raw[:7];parts.append(part);return len(part)
    monkeypatch.setattr(identity.os,'write',write)
    code=identity.main(['emit','--root',str(root)])
    assert code==int(failure)
    assert identity.validate_console(b''.join(parts))is not failure


def test_missing_fresh_capture_flag_rejects_unchanged_valid_seal(owned,monkeypatch,capfd):
    root,_=owned;monkeypatch.delenv('SECURITY_IDENTITY_FRESH_CAPTURE')
    status,raw=emit_cli(root,capfd);assert status==1 and is_invalid(raw)


def test_prepare_failure_before_unlink_cannot_emit_without_fresh_token(owned,monkeypatch,capfd):
    root,_=owned;before=(root/identity.CONTEXT).read_bytes()
    monkeypatch.setattr(identity,'git_bytes',lambda *args:(_ for _ in ()).throw(OSError(CANARY)))
    with pytest.raises(identity.DiagnosticFailure):identity.prepare(root)
    assert (root/identity.CONTEXT).read_bytes()==before
    monkeypatch.delenv('SECURITY_IDENTITY_FRESH_CAPTURE')
    status,raw=emit_cli(root,capfd);assert status==1 and is_invalid(raw)


def test_seal_refuses_tracked_context_without_modification(owned,monkeypatch):
    root,_=owned;prior=(root/identity.CONTEXT).read_bytes()
    monkeypatch.setattr(identity,'git_bytes',lambda *args:b'.security-identity-context.json\0')
    with pytest.raises(ValueError):identity.seal(root)
    assert (root/identity.CONTEXT).read_bytes()==prior


def test_no_prepare_success_flag_invalidates_untracked_seal(owned,monkeypatch):
    root,_=owned;monkeypatch.setenv('SECURITY_IDENTITY_PREPARE_OK','0')
    with pytest.raises(ValueError):identity.seal(root)
    assert not (root/identity.CONTEXT).exists()


_FAILURE_STAGES = {
    'prepare': ('tracked_context', 'context_remove', 'tracked_outputs', 'outputs_remove',
                'capture_bindings', 'context_write'),
    'seal': ('tracked_context', 'context_read', 'context_schema', 'context_bindings',
             'context_remove', 'freshness_flag', 'context_phase', 'report_read',
             'summary_read', 'report_validation', 'context_write'),
    'emit': ('freshness_flag', 'tracked_context', 'context_read', 'context_schema',
             'context_bindings', 'context_phase', 'report_read', 'summary_read',
             'manifest_read', 'artifact_binding', 'report_validation',
             'manifest_validation', 'run_binding', 'output_bounds'),
}


@pytest.mark.parametrize('action,reason', [(action, reason) for action, reasons in _FAILURE_STAGES.items() for reason in reasons])
def test_each_failure_boundary_emits_only_fixed_code(owned, monkeypatch, capfd, action, reason):
    from contextlib import contextmanager
    root, _ = owned
    if action == 'seal':
        context = identity.context_read(root)
        context.update(phase='prepared', artifacts={})
        identity.context_write(root, context)
    original_stage = identity.stage

    @contextmanager
    def injected_stage(actual_reason):
        with original_stage(actual_reason):
            if actual_reason == reason:
                raise OSError(CANARY + '/path?private=hidden')
            yield

    monkeypatch.setattr(identity, 'stage', injected_stage)
    assert identity.main([action, '--root', str(root)]) == 1
    captured = capfd.readouterr()
    assert captured.err == '' and CANARY not in captured.out
    raw = captured.out.encode()
    assert is_invalid(raw)
    value = json.loads(raw)
    assert (value['phase'], value['reason']) == (action, reason)


@pytest.mark.parametrize('action', ['prepare', 'seal', 'emit'])
def test_unexpected_exception_body_is_never_inspected(owned, monkeypatch, capfd, action):
    root, _ = owned

    class HostileError(Exception):
        def __str__(self):
            raise AssertionError('must not inspect exception body')

    def broken(_):
        raise HostileError(CANARY)

    monkeypatch.setattr(identity, action, broken)
    assert identity.main([action, '--root', str(root)]) == 1
    captured = capfd.readouterr()
    assert captured.err == '' and CANARY not in captured.out
    assert is_invalid(captured.out.encode())
    assert json.loads(captured.out)['reason'] == 'unexpected'


@pytest.mark.parametrize('phase', list(identity.PHASES) + [CANARY, None, [], {'private': CANARY}])
@pytest.mark.parametrize('reason', list(identity.REASONS) + [CANARY, None, [], {'private': CANARY}])
def test_invalid_vocabulary_is_finite_and_never_reflects_input(phase, reason):
    raw = identity.invalid_record(phase, reason)
    assert is_invalid(raw) and CANARY.encode() not in raw


def test_real_malformed_seal_is_identified_without_relaxing_schema(owned, capfd):
    root, _ = owned
    context = identity.context_read(root)
    context.update(phase='prepared', artifacts={})
    identity.context_write(root, context)
    report = [finding()]
    report[0]['Tags'] = None
    (root / identity.REPORT).write_bytes(identity.canonical(report))
    assert identity.main(['seal', '--root', str(root)]) == 1
    captured = capfd.readouterr()
    assert captured.err == '' and CANARY not in captured.out
    assert json.loads(captured.out) == {'schema': 'nico.security-identity.v1', 'state': 'invalid',
                                     'phase': 'seal', 'reason': 'report_validation'}
    assert not (root / identity.CONTEXT).exists()


def test_cli_failure_reasons_do_not_reflect_arguments(owned, capfd):
    root, _ = owned
    for args, phase, reason in [(['--unknown', CANARY], 'cli', 'arguments'),
                                (['emit', '--root', str(root / CANARY)], 'emit', 'root')]:
        assert identity.main(args) == 1
        captured = capfd.readouterr()
        assert captured.err == '' and CANARY not in captured.out
        value = json.loads(captured.out)
        assert (value['phase'], value['reason']) == (phase, reason)
