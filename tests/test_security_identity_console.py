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
                                     'phase': 'seal', 'reason': 'finding_tags_list'}
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


# Report-only reason refinement: all fixtures are synthetic and retain old limits.
def report_summary(count=1):
    return {'scanner': 'gitleaks', 'status': 'completed', 'finding_count': count,
            'artifact_present': True, 'history_depth': 'full', 'exit_code': 1 if count else 0}


def assert_report_reason(report, summary, reason):
    with pytest.raises(identity.DiagnosticFailure) as error:
        identity.parse_findings(report, summary)
    assert error.value.reason == reason
    raw = identity.invalid_record('seal', error.value.reason)
    assert len(raw) <= 512 and CANARY.encode() not in raw
    assert json.loads(raw)['reason'] == reason


@pytest.mark.parametrize('which', ['report', 'summary'])
@pytest.mark.parametrize('raw,suffix', [
    (None, 'raw_type'), (b'', 'raw_empty'), (b'x' * (identity.LIMIT + 1), 'raw_size'),
    (b'\xff', 'utf8'), (b'{"x":1,"x":2}', 'duplicate_keys'),
    (b'[NaN]', 'nonfinite_json'), (b'{', 'json_syntax'),
])
def test_raw_report_and_summary_have_distinct_fixed_decode_codes(which, raw, suffix):
    report = identity.canonical([finding()])
    summary = identity.canonical(report_summary())
    if which == 'report':
        report = raw
    else:
        summary = raw
    assert_report_reason(report, summary, which + '_' + suffix)


@pytest.mark.parametrize('field,value,reason', [
    ('scanner', 'other', 'summary_scanner'), ('status', 'unavailable', 'summary_status'),
    ('artifact_present', 1, 'summary_artifact_present'), ('history_depth', 'shallow', 'summary_history_depth'),
    ('finding_count', True, 'summary_count_type'), ('finding_count', -1, 'summary_count_range'),
    ('finding_count', 10**12 + 1, 'summary_count_range'), ('finding_count', 2, 'summary_count_match'),
    ('exit_code', True, 'summary_exit_type'), ('exit_code', 0, 'summary_exit_value'),
])
def test_each_summary_predicate_has_its_own_reason(field, value, reason):
    summary = report_summary()
    summary[field] = value
    assert_report_reason(identity.canonical([finding()]), identity.canonical(summary), reason)


@pytest.mark.parametrize('field,prefix,limit', [
    ('Commit', 'finding_commit', 40), ('File', 'finding_path', 4096),
    ('RuleID', 'finding_rule', 256), ('Fingerprint', 'finding_fingerprint', 8192),
    ('Match', 'finding_match', 65536), ('Description', 'finding_description', 16384),
    ('Author', 'finding_author', 16384), ('Email', 'finding_email', 16384),
    ('Date', 'finding_date', 16384), ('Message', 'finding_message', identity.LIMIT),
    ('SymlinkFile', 'finding_symlink_file', 16384), ('Link', 'finding_link', 16384),
])
@pytest.mark.parametrize('failure', ['type', 'encoding', 'bytes'])
def test_text_check_codes_are_field_specific_without_echoing_values(field, prefix, limit, failure):
    item = finding()
    item[field] = None if failure == 'type' else '\ud800' if failure == 'encoding' else 'x' * (limit + 1)
    # JSON ASCII escapes carry the invalid surrogate to the existing UTF8 predicate.
    report = json.dumps([item], ensure_ascii=True).encode()
    reason = 'report_raw_size' if field == 'Message' and failure == 'bytes' else prefix + '_' + failure
    assert_report_reason(report, identity.canonical(report_summary()), reason)


@pytest.mark.parametrize('field,prefix', [
    ('StartLine', 'finding_start_line'), ('EndLine', 'finding_end_line'),
    ('StartColumn', 'finding_start_column'), ('EndColumn', 'finding_end_column'),
])
@pytest.mark.parametrize('value,suffix', [(True, 'type'), (1.0, 'type'), (0, 'range'), (10**9 + 1, 'range')])
def test_position_types_and_ranges_are_distinguished(field, prefix, value, suffix):
    item = finding()
    item[field] = value
    assert_report_reason(identity.canonical([item]), identity.canonical(report_summary()), prefix + '_' + suffix)


@pytest.mark.parametrize('change,reason', [
    ({'Commit': 'z' * 40}, 'finding_commit_hex'),
    ({'File': ''}, 'finding_path_empty'), ({'File': '/owned'}, 'finding_path_absolute'),
    ({'File': 'x\\y'}, 'finding_path_backslash'), ({'File': 'x/../y'}, 'finding_path_components'),
    ({'File': 'x\ny'}, 'finding_path_control'), ({'RuleID': ''}, 'finding_rule_empty'),
    ({'RuleID': 'x\ny'}, 'finding_rule_control'),
    ({'StartLine': 2, 'EndLine': 1}, 'finding_line_order'),
    ({'StartColumn': 3, 'EndColumn': 2}, 'finding_column_order'),
    ({'Fingerprint': CANARY}, 'finding_fingerprint_match'),
    ({'Secret': False}, 'finding_secret_type'), ({'Secret': CANARY}, 'finding_secret_marker'),
    ({'Match': CANARY}, 'finding_match_redaction'),
    ({'Entropy': True}, 'finding_entropy_type'), ({'Entropy': -1}, 'finding_entropy_range'),
    ({'Entropy': 101}, 'finding_entropy_range'),
    ({'Tags': None}, 'finding_tags_list'), ({'Tags': [''] * 129}, 'finding_tags_count'),
    ({'Tags': [1]}, 'finding_tag_type'), ({'Tags': ['x' * 257]}, 'finding_tag_bytes'),
])
def test_structural_guards_emit_only_their_fixed_check(change, reason):
    item = finding()
    item.update(change)
    assert_report_reason(identity.canonical([item]), identity.canonical(report_summary()), reason)


@pytest.mark.parametrize('which', ['report', 'summary'])
def test_numeric_decode_bound_remains_rejected(which):
    import sys
    bound = sys.get_int_max_str_digits()
    if not bound:
        pytest.skip('interpreter integer digit limit disabled; no decode-number failure to observe')
    raw = b'9' * (bound + 1)
    report, summary = identity.canonical([finding()]), identity.canonical(report_summary())
    assert_report_reason(raw if which == 'report' else report,
                         raw if which == 'summary' else summary, which + '_json_value_error')


def test_entropy_nonfinite_and_conversion_overflow_remain_rejected():
    # Exponent overflow is accepted by JSON decoding, then rejected by math.isfinite.
    report = identity.canonical([finding()]).replace(b'"Entropy":1.5', b'"Entropy":1e999')
    assert_report_reason(report, identity.canonical(report_summary()), 'finding_entropy_finite')
    item = finding()
    item['Entropy'] = 10**400
    assert_report_reason(identity.canonical([item]), identity.canonical(report_summary()), 'finding_entropy_finite_check_overflow')


def test_collection_shapes_and_duplicate_occurrence_codes():
    summary = identity.canonical(report_summary())
    assert_report_reason(b'{}', summary, 'report_list')
    assert_report_reason(identity.canonical([finding()]), b'[]', 'summary_dict')
    assert_report_reason(identity.canonical([finding()]), b'{}', 'summary_keys')
    assert_report_reason(b'[0]', summary, 'finding_dict')
    assert_report_reason(b'[{}]', summary, 'finding_required_keys')
    item = finding()
    item['Verified'] = False
    assert_report_reason(identity.canonical([item]), summary, 'finding_extra_keys')
    assert_report_reason(identity.canonical([finding(), finding()]),
                         identity.canonical(report_summary(2)), 'finding_duplicate_occurrence')
    n = identity.MAX_RECORDS - len(identity.BINDINGS) - 2
    assert_report_reason(identity.canonical([finding(i) for i in range(n)]),
                         identity.canonical(report_summary(n)), 'report_count_cap')


def test_tag_encoding_code_never_contains_element_or_index():
    item = finding()
    item['Tags'] = ['\ud800']
    assert_report_reason(json.dumps([item]).encode(), identity.canonical(report_summary()), 'finding_tag_encoding')


@pytest.mark.parametrize('field', ['Description', 'Author', 'Email', 'Date', 'SymlinkFile', 'Link'])
def test_optional_text_byte_boundary_is_unchanged(field):
    item = finding()
    item[field] = '\u00e9' * 8192  # Exactly16384 UTF8 bytes; character count is smaller.
    assert identity.parse_findings(identity.canonical([item]), identity.canonical(report_summary()))[0]['finding'] == item
    item[field] += 'x'
    with pytest.raises(identity.DiagnosticFailure) as error:
        identity.parse_findings(identity.canonical([item]), identity.canonical(report_summary()))
    assert error.value.reason in identity.REPORT_REASONS and error.value.reason.endswith('_bytes')


@pytest.mark.parametrize('which', ['report', 'summary'])
def test_decoder_depth_exception_has_a_fixed_boundary(which):
    # CPython 3.12's JSON C-stack bound differs from sys.getrecursionlimit().
    # This bounded synthetic input exceeds both supported runtime limits.
    depth = 10000
    raw = b'[' * depth + b'0' + b']' * depth
    assert len(raw) <= identity.LIMIT
    report, summary = identity.canonical([finding()]), identity.canonical(report_summary())
    assert_report_reason(raw if which == 'report' else report,
                         raw if which == 'summary' else summary, which + '_json_depth')


def test_every_report_reason_has_an_actual_invalid_input(monkeypatch):
    # Execute the category fixtures, collecting observed reasons rather than
    # merely checking that arbitrary strings belong to the vocabulary.
    import itertools
    observed = set()
    original = assert_report_reason

    def observe(report, summary, reason):
        original(report, summary, reason)
        observed.add(reason)

    monkeypatch.setitem(globals(), 'assert_report_reason', observe)
    cases = [
        test_raw_report_and_summary_have_distinct_fixed_decode_codes,
        test_each_summary_predicate_has_its_own_reason,
        test_text_check_codes_are_field_specific_without_echoing_values,
        test_position_types_and_ranges_are_distinguished,
        test_structural_guards_emit_only_their_fixed_check,
        test_numeric_decode_bound_remains_rejected,
        test_entropy_nonfinite_and_conversion_overflow_remain_rejected,
        test_collection_shapes_and_duplicate_occurrence_codes,
        test_tag_encoding_code_never_contains_element_or_index,
        test_decoder_depth_exception_has_a_fixed_boundary,
    ]
    for case in cases:
        dimensions = []
        for mark in getattr(case, 'pytestmark', []):
            if mark.name == 'parametrize':
                names = [name.strip() for name in mark.args[0].split(',')]
                dimensions.append([
                    dict(zip(names, (value,) if len(names) == 1 else value))
                    for value in mark.args[1]
                ])
        for combination in itertools.product(*dimensions):
            arguments = {key: value for mapping in combination for key, value in mapping.items()}
            case(**arguments)
    # Message's per-string bound cannot precede the stricter complete JSON byte cap.
    assert observed == identity.REPORT_REASONS - {'finding_message_bytes'}


@pytest.mark.parametrize('message', ['', 'x' * 16384, 'x' * 16385, '\u00e9' * 8193])
def test_message_compatibility_preserves_identity_and_content(message):
    item = finding()
    summary = identity.canonical(report_summary())
    before = identity.parse_findings(identity.canonical([item]), summary)[0]
    item['Message'] = message
    raw = identity.canonical([item])
    after = identity.parse_findings(raw, summary)[0]
    assert after['finding']['Message'] == message
    assert after['fingerprint_sha256'] == before['fingerprint_sha256']
    assert after['shape_hash'] == before['shape_hash']
    assert identity.digest(raw) != identity.digest(identity.canonical([finding()]))


def message_report_at_cap(records, unicode=False):
    data = [finding(i) for i in range(records)]
    for item in data:
        item['Message'] = ''
    available = identity.LIMIT - len(identity.canonical(data))
    for index, item in enumerate(data):
        budget = available // (records - index)
        item['Message'] = ('\u00e9' * (budget // 2) + 'x' * (budget % 2)) if unicode else 'x' * budget
        available -= budget
    raw = identity.canonical(data)
    assert len(raw) == identity.LIMIT
    return data, raw


@pytest.mark.parametrize('records', [1, 2, 3])
@pytest.mark.parametrize('unicode', [False, True])
def test_complete_report_cap_still_governs_all_messages(records, unicode):
    data, raw = message_report_at_cap(records, unicode)
    summary = identity.canonical(report_summary(records))
    assert len(identity.parse_findings(raw, summary)) == records
    data[-1]['Message'] += 'x'
    overflow = identity.canonical(data)
    assert len(overflow) == identity.LIMIT + 1
    assert_report_reason(overflow, summary, 'report_raw_size')


@pytest.mark.parametrize('message', [None, True, False, 1, 1.5, [], {}, ['owned']])
def test_message_type_contract_remains_strict(message):
    item = finding()
    item['Message'] = message
    assert_report_reason(identity.canonical([item]), identity.canonical(report_summary()), 'finding_message_type')


def test_message_direct_text_bound_and_encoding_are_preserved():
    codes = identity.REPORT_TEXT_CODES['Message']
    assert len(identity.report_text('x' * identity.LIMIT, identity.LIMIT, codes)) == identity.LIMIT
    with pytest.raises(identity.DiagnosticFailure) as error:
        identity.report_text('x' * (identity.LIMIT + 1), identity.LIMIT, codes)
    assert error.value.reason == 'finding_message_bytes'
    item = finding()
    item['Message'] = '\ud800'
    assert_report_reason(json.dumps([item]).encode(), identity.canonical(report_summary()), 'finding_message_encoding')


def test_long_message_fresh_synthetic_lifecycle_does_not_disclose_or_ignore_mutation(owned, capfd):
    root, build = owned
    item = finding()
    item['Message'] = CANARY * 2000
    build([item])
    report = (root / identity.REPORT).read_bytes()
    status, raw = emit_cli(root, capfd)
    assert status == 0 and identity.validate_console(raw)
    assert json.loads(raw.splitlines()[0])['report_sha256'] == identity.digest(report)
    item['Message'] += 'x'
    (root / identity.REPORT).write_bytes(identity.canonical([item]))
    status, raw = emit_cli(root, capfd)
    assert status == 1 and json.loads(raw)['reason'] == 'artifact_binding'
