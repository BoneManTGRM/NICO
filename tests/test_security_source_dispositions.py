"""Synthetic controls only: no retained report or actual finding metadata fixtures."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml
from scripts import security_source_dispositions as subject
from scripts import security_audit_gate as gate
from tests.test_security_audit_gate import _clean_evidence, _write


def synthetic(index):
    line = max(1, index)
    finding = dict(Commit='a'*40, File='owned/公開-digests.txt', RuleID='generic-api-key',
                   StartLine=line, EndLine=line, StartColumn=1, EndColumn=30,
                   Secret='REDACTED', Match='owned公開 = "REDACTED"', Message='owned commit')
    if index == 0:
        finding.update(StartColumn=40, EndColumn=69)
    finding['Fingerprint'] = f"{finding['Commit']}:{finding['File']}:{finding['RuleID']}:{line}"
    return finding


def independent_pair(finding):
    occurrence = [finding[key] for key in ('Commit','File','RuleID','StartLine','EndLine','StartColumn','EndColumn')]
    shape = [*occurrence, finding['Fingerprint'], hashlib.sha256(finding['Match'].encode()).hexdigest(), 'REDACTED','verified_absent']
    raw = json.dumps(shape, sort_keys=True, separators=(',',':'), ensure_ascii=False).encode()
    return hashlib.sha256(finding['Fingerprint'].encode()).hexdigest(), hashlib.sha256(raw).hexdigest()


def summary(count):
    return dict(scanner='gitleaks',status='completed',finding_count=count,
                artifact_present=True,history_depth='full',exit_code=int(bool(count)))


@pytest.fixture
def approved(monkeypatch):
    data = [synthetic(index) for index in range(23)]
    pairs = frozenset(independent_pair(item) for item in data)
    assert len(pairs)==23 and len({pair[0] for pair in pairs})==22
    monkeypatch.setattr(subject,'_approved_bindings',lambda:pairs)
    return data


def indices(data):
    meta=summary(len(data))
    return subject.approved_indices(subject._canonical(data),subject._canonical(meta),data,meta)


def write_capture(root,data):
    raw=subject._canonical(data)
    (root/'gitleaks.json').write_bytes(raw)
    (root/'gitleaks-summary.json').write_bytes(subject._canonical(summary(len(data))))
    return raw


def test_real_manifest_is_exact_pinned_hash_only_34_shapes_32_fingerprints():
    assert hashlib.sha256(subject.MANIFEST.read_bytes()).hexdigest()==subject.MANIFEST_SHA256
    pairs=subject._approved_bindings()
    assert len(pairs)==34 and len({p[0]for p in pairs})==32
    entries=json.loads(subject.MANIFEST.read_bytes())['entries']
    assert all(set(entry)=={'classification','current_disposition','fingerprint_sha256',
        'immutable_location_blob_sha256','proposed_disposition','provenance_group','shape_sha256'}for entry in entries)


def test_all_synthetic_23_unicode_identities_and_shared_fingerprint_columns(approved):
    assert indices(approved)==frozenset(range(23))
    assert approved[0]['Fingerprint']==approved[1]['Fingerprint']
    for finding in approved:
        assert subject._identity(finding)[1]==independent_pair(finding)


@pytest.mark.parametrize('index',range(23))
@pytest.mark.parametrize('field',sorted(subject.REQUIRED))
def test_each_bound_field_change_and_missing_field_cannot_approve(approved,index,field):
    changed=deepcopy(approved)
    value=changed[index][field]
    changed[index][field]=value+1 if type(value)is int else value+' changed'
    assert index not in indices(changed)
    changed=deepcopy(approved);del changed[index][field]
    assert not indices(changed)


@pytest.mark.parametrize('value',[False,True,None,0,'false'])
def test_verified_any_presence_rejects_whole_new_approval_capture(approved,value):
    approved[0]['Verified']=value
    assert not indices(approved)


@pytest.mark.parametrize('field,value',[
    ('StartLine',True),('EndLine',1.0),('StartColumn',0),('EndColumn',10**9+1),
    ('Commit',None),('File','../outside'),('RuleID','line\nbreak'),('Secret',None),
    ('Match','not redacted'),('Message',None),('Message','\ud800'),('Entropy',True),
    ('Entropy',float('inf')),('Entropy',10**400),('Tags',None),('Tags',[False]),
    ('Tags',['x'*257]),('Tags',['x']*129),('unexpected','value'),
])
def test_malformed_fields_fail_closed_without_metadata_coercion(approved,field,value):
    approved[0][field]=value
    raw=json.dumps(approved).encode()
    meta=summary(len(approved))
    assert not subject.approved_indices(raw,subject._canonical(meta),approved,meta)


def test_optional_fields_are_validated_but_are_not_identity_authentication(approved):
    approved[0].update(Message='x'*20000,Description='owned',Author='owned',Email='owned',
                       Date='owned',SymlinkFile='',Link='',Entropy=1.5,Tags=['owned'])
    assert indices(approved)==frozenset(range(23))
    approved[0]['Description']='x'*16385
    assert not indices(approved)


@pytest.mark.parametrize('field,value',[
    ('scanner','other'),('status','failed'),('finding_count',True),('finding_count',22),
    ('artifact_present',1),('history_depth','shallow'),('exit_code',True),('exit_code',0),
    ('extra',False),
])
def test_incomplete_or_changed_summary_gets_no_new_approvals(approved,field,value):
    meta=summary(len(approved));meta[field]=value
    assert not subject.approved_indices(subject._canonical(approved),subject._canonical(meta),approved,meta)


@pytest.mark.parametrize('which',['report','summary'])
@pytest.mark.parametrize('raw',[b'',b'{',b'\xff',b'{"x":1,"x":2}',b'[NaN]',b'x'*(subject.LIMIT+1)])
def test_raw_invalid_truncated_duplicate_or_oversized_capture(approved,which,raw):
    meta=summary(len(approved));report=subject._canonical(approved);meta_raw=subject._canonical(meta)
    assert not subject.approved_indices(raw if which=='report'else report,
        raw if which=='summary'else meta_raw,approved,meta)


def test_duplicate_occurrences_and_over_cap_receive_no_new_approvals(approved):
    assert not indices(approved+[approved[0]])
    many=[synthetic(i+100)for i in range(111)]
    assert not indices(many)


def test_second_snapshot_disagreement_including_bool_int_is_rejected(approved):
    meta=summary(23);raw=subject._canonical(approved);meta_raw=subject._canonical(meta)
    changed=deepcopy(approved);changed[0]['StartLine']=True
    assert not subject.approved_indices(raw,meta_raw,changed,meta)
    assert not subject.approved_indices(raw,meta_raw,approved,{**meta,'exit_code':True})


def test_67_findings_retained_and_all_unknown_findings_block(approved,tmp_path):
    data=approved+[synthetic(i+100)for i in range(44)]
    raw=write_capture(tmp_path,data);result=gate._gitleaks(tmp_path)
    assert result['finding_count']==len(result['triage'])==67
    assert result['approved_public_source_hashes']==23 and result['blocking']==44
    assert (tmp_path/'gitleaks.json').read_bytes()==raw
    assert [row['disposition']for row in result['triage']]==['approved_public_source_hash']*23+['blocking']*44


def test_prior_disposition_preserved_when_new_capture_validation_fails(approved,tmp_path):
    data=[*approved,dict(synthetic(100),File='tests/owned_fixture.py')]
    data[0]['Verified']=False
    write_capture(tmp_path,data);result=gate._gitleaks(tmp_path)
    assert result['blocking']==23 and result['approved_test_placeholders']==1


def test_unavailable_manifest_and_changed_manifest_never_approve(approved,tmp_path,monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(subject,'MANIFEST',tmp_path/'missing')
    assert not indices(approved)
    subject.MANIFEST.write_bytes(b'{}')
    assert not indices(approved)


def test_bounded_reader_rejects_nonregular_and_symlink_inputs(tmp_path,approved):
    raw=write_capture(tmp_path,approved);report=tmp_path/'gitleaks.json';report.unlink()
    target=tmp_path/'owned';target.write_bytes(raw);report.symlink_to(target)
    assert not subject.approved_indices_from_files(tmp_path,approved,summary(23))
    report.unlink()
    import os
    os.mkfifo(report)
    assert not subject.approved_indices_from_files(tmp_path,approved,summary(23))


def test_enforcement_and_26_review_items_are_unchanged(approved,tmp_path,monkeypatch,capsys):
    _clean_evidence(tmp_path);write_capture(tmp_path,approved)
    _write(tmp_path,'semgrep.json',{'results':[{'check_id':'owned-review','path':'owned.py'}for _ in range(26)],'errors':[]})
    manifest=gate.build_manifest(tmp_path)
    assert manifest['tools']['semgrep']['finding_count']==26
    assert manifest['security_gate']['status']=='passed' and manifest['security_gate']['review_required']
    assert manifest['human_review_required'] is True and manifest['client_delivery_allowed'] is False
    monkeypatch.setattr(sys,'argv',['gate','--root',str(tmp_path),'--enforce'])
    assert gate.main()==0
    write_capture(tmp_path,approved+[synthetic(1000)])
    assert gate.main()==1
    (tmp_path/'gitleaks.json').write_bytes(b'{')
    assert gate.main()==1
    capsys.readouterr()


def test_workflow_retains_always_run_collection_upload_and_enforcement():
    workflow=yaml.safe_load(Path('.github/workflows/security-audit.yml').read_text())
    steps=[s for job in workflow['jobs'].values()for s in job.get('steps',[])]
    for name in ['Build fail-closed scanner manifest','Upload audit evidence before enforcement','Require complete clean security evidence']:
        assert next(s for s in steps if s.get('name')==name)['if']=='always()'
    assert '--enforce --require-sanitized-trufflehog' in next(s for s in steps if s.get('name')=='Require complete clean security evidence')['run']


@pytest.mark.parametrize('field',sorted(summary(23)))
def test_missing_summary_field_never_approves(approved,field):
    meta=summary(23);del meta[field]
    assert not subject.approved_indices(subject._canonical(approved),subject._canonical(meta),approved,meta)


def test_manifest_mutation_is_rejected_by_actual_pinned_loader(tmp_path,monkeypatch):
    raw=subject.MANIFEST.read_bytes()
    path=tmp_path/'manifest.json';path.write_bytes(raw)
    monkeypatch.setattr(subject,'MANIFEST',path)
    assert len(subject._approved_bindings())==34
    value=json.loads(raw);value['entries'][0]['immutable_location_blob_sha256']='0'*64
    path.write_bytes(subject._canonical(value))
    with pytest.raises(ValueError,match='invalid_source_disposition_capture'):
        subject._approved_bindings()


def test_26_nonfatal_semgrep_diagnostics_remain_partial_and_review_required(approved,tmp_path,monkeypatch,capsys):
    _clean_evidence(tmp_path);write_capture(tmp_path,approved)
    _write(tmp_path,'semgrep.json',{'results':[],'errors':[
        {'level':'warn','type':'PartialParsing','message':'owned diagnostic'}for _ in range(26)]})
    manifest=gate.build_manifest(tmp_path);record=manifest['tools']['semgrep']
    assert record['diagnostic_count']==26 and record['finding_count']==0
    assert record['capture_complete'] is False and manifest['partial_capture_tools']==['semgrep']
    assert manifest['security_gate']['status']=='passed'
    assert any('partial capture' in item for item in manifest['security_gate']['review_required'])
    monkeypatch.setattr(sys,'argv',['gate','--root',str(tmp_path),'--enforce'])
    assert gate.main()==0
    for level in ['error','fatal']:
        _write(tmp_path,'semgrep.json',{'results':[],'errors':[{'level':level,'message':'owned'}]})
        assert gate.main()==1
    _write(tmp_path,'semgrep.json',{'results':[{'check_id':next(iter(gate.SEMGREP_BLOCKING_RULES)), 'path':'owned.yml'}],'errors':[]})
    assert gate.main()==1
    capsys.readouterr()


def test_exact_capture_count_and_byte_boundaries(approved):
    data=approved+[synthetic(i+100)for i in range(subject.MAX_FINDINGS-len(approved))]
    assert indices(data)==frozenset(range(23))
    assert not indices(data+[synthetic(1000)])
    data=deepcopy(approved)
    data[0]['Message']=''
    remaining=subject.LIMIT-len(subject._canonical(data))
    data[0]['Message']='x'*remaining
    raw=subject._canonical(data);assert len(raw)==subject.LIMIT
    meta=summary(len(data));meta_raw=subject._canonical(meta)
    assert subject.approved_indices(raw,meta_raw,data,meta)==frozenset(range(23))
    data[0]['Message']+='x'
    assert not subject.approved_indices(subject._canonical(data),meta_raw,data,meta)


def test_deeply_nested_json_is_rejected_without_output(approved,capsys):
    raw=b'['*10000+b'0'+b']'*10000
    meta=summary(len(approved))
    assert not subject.approved_indices(raw,subject._canonical(meta),approved,meta)
    output=capsys.readouterr();assert output.out==output.err==''
