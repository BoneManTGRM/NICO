"""Reviewed bounded identity parsing utilities reused from the local identity diagnostic.
No standalone capture or emission workflow is exposed here."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import selectors
import time
import shutil
import stat
import subprocess
import tempfile

try:
    from . import security_audit_gate as gate
except ImportError:
    import security_audit_gate as gate

LIMIT=4*1024*1024
MAX_RECORDS=128
MAX_RECORD_BYTES=512
MAX_OUTPUT=65536
CONTEXT='.security-identity-context.json'
REPORT='gitleaks.json'
SUMMARY='gitleaks-summary.json'
MANIFEST='scanner-worker-artifact.json'
BINDINGS=('head','tree','pr_head','base','run','attempt','tool','config','helper','workflow','refset','invocation','ignore','tool_policy','nonce')
DISPOSITIONS={'blocking':'blocking','approved_test_placeholder':'approved_test_placeholders',
    'approved_public_verifier_digest':'approved_public_verifiers',
    'approved_public_signing_fingerprint':'approved_public_signing_fingerprints',
    'approved_public_source_hash':'approved_public_source_hashes'}
PHASES = frozenset({'cli', 'prepare', 'seal', 'emit'})
REASONS = frozenset({
    'unexpected', 'arguments', 'root', 'tracked_context', 'context_remove',
    'tracked_outputs', 'outputs_remove', 'capture_bindings', 'context_read',
    'context_schema', 'context_bindings', 'context_write', 'freshness_flag',
    'context_phase', 'report_read', 'summary_read', 'report_validation',
    'manifest_read', 'artifact_binding', 'manifest_validation', 'run_binding',
    'output_bounds',
})


# Literal-only diagnostic vocabulary. No input field/value is used as a reason.
REPORT_DECODE_CODES = {
    'report': ('report_raw_type', 'report_raw_empty', 'report_raw_size', 'report_utf8', 'report_duplicate_keys', 'report_nonfinite_json', 'report_json_syntax', 'report_json_depth', 'report_json_value_error'),
    'summary': ('summary_raw_type', 'summary_raw_empty', 'summary_raw_size', 'summary_utf8', 'summary_duplicate_keys', 'summary_nonfinite_json', 'summary_json_syntax', 'summary_json_depth', 'summary_json_value_error'),
}
REPORT_TEXT_CODES = {
    'Commit': ('finding_commit_type', 'finding_commit_encoding', 'finding_commit_bytes'),
    'File': ('finding_path_type', 'finding_path_encoding', 'finding_path_bytes'),
    'RuleID': ('finding_rule_type', 'finding_rule_encoding', 'finding_rule_bytes'),
    'Fingerprint': ('finding_fingerprint_type', 'finding_fingerprint_encoding', 'finding_fingerprint_bytes'),
    'Match': ('finding_match_type', 'finding_match_encoding', 'finding_match_bytes'),
    'Description': ('finding_description_type', 'finding_description_encoding', 'finding_description_bytes'),
    'Author': ('finding_author_type', 'finding_author_encoding', 'finding_author_bytes'),
    'Email': ('finding_email_type', 'finding_email_encoding', 'finding_email_bytes'),
    'Date': ('finding_date_type', 'finding_date_encoding', 'finding_date_bytes'),
    'Message': ('finding_message_type', 'finding_message_encoding', 'finding_message_bytes'),
    'SymlinkFile': ('finding_symlink_file_type', 'finding_symlink_file_encoding', 'finding_symlink_file_bytes'),
    'Link': ('finding_link_type', 'finding_link_encoding', 'finding_link_bytes'),
    'Tag': ('finding_tag_type', 'finding_tag_encoding', 'finding_tag_bytes'),
}
REPORT_POSITION_CODES = {
    'StartLine': ('finding_start_line_type', 'finding_start_line_range'),
    'EndLine': ('finding_end_line_type', 'finding_end_line_range'),
    'StartColumn': ('finding_start_column_type', 'finding_start_column_range'),
    'EndColumn': ('finding_end_column_type', 'finding_end_column_range'),
}
REPORT_CHECK_CODES = frozenset({
    'report_list',
    'report_count_cap',
    'summary_dict',
    'summary_keys',
    'summary_scanner',
    'summary_status',
    'summary_artifact_present',
    'summary_history_depth',
    'summary_count_type',
    'summary_count_range',
    'summary_count_match',
    'summary_exit_type',
    'summary_exit_value',
    'finding_dict',
    'finding_required_keys',
    'finding_extra_keys',
    'finding_commit_hex',
    'finding_path_empty',
    'finding_path_absolute',
    'finding_path_backslash',
    'finding_path_components',
    'finding_path_control',
    'finding_rule_empty',
    'finding_rule_control',
    'finding_line_order',
    'finding_column_order',
    'finding_fingerprint_match',
    'finding_secret_type',
    'finding_secret_marker',
    'finding_match_redaction',
    'finding_entropy_type',
    'finding_entropy_finite',
    'finding_entropy_finite_check_overflow',
    'finding_entropy_range',
    'finding_tags_list',
    'finding_tags_count',
    'finding_duplicate_occurrence',
})
REPORT_REASONS = REPORT_CHECK_CODES | frozenset(
    code for mapping in (REPORT_DECODE_CODES, REPORT_TEXT_CODES, REPORT_POSITION_CODES)
    for codes in mapping.values() for code in codes
)
REASONS = REASONS | REPORT_REASONS


class DiagnosticFailure(ValueError):
    def __init__(self, reason):
        # Only internal fixed codes are retained; exception messages never are.
        self.reason = reason if type(reason) is str and reason in REASONS else 'unexpected'
        super().__init__()


@contextmanager
def stage(reason):
    try:
        yield
    except DiagnosticFailure:
        raise
    except (Exception, SystemExit):
        raise DiagnosticFailure(reason) from None


def invalid_record(phase, reason):
    phase = phase if type(phase) is str and phase in PHASES else 'cli'
    reason = reason if type(reason) is str and reason in REASONS else 'unexpected'
    return (json.dumps({'schema': 'nico.security-identity.v1', 'state': 'invalid',
                        'phase': phase, 'reason': reason},
                       sort_keys=True, separators=(',', ':')).encode('ascii') + b'\n')

INVOKE=['gitleaks','detect','--source','.','--report-format','json','--report-path',REPORT,'--no-banner','--redact']


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')


def digest(raw):return hashlib.sha256(raw).hexdigest()
def require(value):
    if not value:raise ValueError('invalid')
def integer(value,upper=10**12):return type(value)is int and 0<=value<=upper
def sha(value):return type(value)is str and re.fullmatch('[0-9a-f]{64}',value)is not None

def pairs(items):
    result={}
    for key,value in items:
        require(key not in result);result[key]=value
    return result

def decode(raw):
    require(type(raw)is bytes and 0<len(raw)<=LIMIT)
    return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,
                      parse_constant=lambda _:(_ for _ in ()).throw(ValueError('invalid')))


def read(path,limit=LIMIT):
    require(path==path.resolve(strict=True))
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd);require(stat.S_ISREG(before.st_mode)and 0<before.st_size<=limit)
        with os.fdopen(fd,'rb',closefd=False)as stream:raw=stream.read(limit+1)
        after=os.fstat(fd)
        require(len(raw)==before.st_size and (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns))
        return raw
    finally:os.close(fd)


def text(value,limit=16384):
    require(type(value)is str and len(value.encode('utf-8'))<=limit)
    return value


def report_check(condition, reason):
    if not condition:
        raise DiagnosticFailure(reason)


def report_text(value, limit, codes):
    type_code, encoding_code, bytes_code = codes
    report_check(type(value) is str, type_code)
    try:
        encoded = value.encode('utf-8')
    except UnicodeEncodeError:
        raise DiagnosticFailure(encoding_code) from None
    report_check(len(encoded) <= limit, bytes_code)
    return value


def report_decode(raw, codes):
    (type_code, empty_code, size_code, utf8_code, duplicate_code,
     nonfinite_code, syntax_code, depth_code, value_error_code) = codes
    report_check(type(raw) is bytes, type_code)
    report_check(len(raw) > 0, empty_code)
    report_check(len(raw) <= LIMIT, size_code)
    try:
        decoded = raw.decode('utf-8')
    except UnicodeDecodeError:
        raise DiagnosticFailure(utf8_code) from None

    def unique_pairs(items):
        result = {}
        for key, value in items:
            report_check(key not in result, duplicate_code)
            result[key] = value
        return result

    def nonfinite(_):
        raise DiagnosticFailure(nonfinite_code)

    try:
        return json.loads(decoded, object_pairs_hook=unique_pairs, parse_constant=nonfinite)
    except DiagnosticFailure:
        raise
    except json.JSONDecodeError:
        raise DiagnosticFailure(syntax_code) from None
    except RecursionError:
        raise DiagnosticFailure(depth_code) from None
    except ValueError:
        # Preserve a distinct decoder ValueError boundary without inferring its cause.
        raise DiagnosticFailure(value_error_code) from None


def parse_findings(raw, summary_raw):
    data = report_decode(raw, REPORT_DECODE_CODES['report'])
    summary = report_decode(summary_raw, REPORT_DECODE_CODES['summary'])
    report_check(type(data) is list, 'report_list')
    report_check(len(data) <= MAX_RECORDS - len(BINDINGS) - 3, 'report_count_cap')
    report_check(type(summary) is dict, 'summary_dict')
    report_check(set(summary) == {
        'scanner', 'status', 'finding_count', 'artifact_present', 'history_depth', 'exit_code'
    }, 'summary_keys')
    report_check(summary['scanner'] == 'gitleaks', 'summary_scanner')
    report_check(summary['status'] == 'completed', 'summary_status')
    report_check(summary['artifact_present'] is True, 'summary_artifact_present')
    report_check(summary['history_depth'] == 'full', 'summary_history_depth')
    report_check(type(summary['finding_count']) is int, 'summary_count_type')
    report_check(0 <= summary['finding_count'] <= 10**12, 'summary_count_range')
    report_check(summary['finding_count'] == len(data), 'summary_count_match')
    report_check(type(summary['exit_code']) is int, 'summary_exit_type')
    report_check(summary['exit_code'] == (1 if data else 0), 'summary_exit_value')
    seen_occurrences = set()
    result = []
    required = {'Commit', 'File', 'RuleID', 'StartLine', 'EndLine', 'StartColumn',
                'EndColumn', 'Fingerprint', 'Match', 'Secret'}
    strings = ('Description', 'Author', 'Email', 'Date', 'Message', 'SymlinkFile', 'Link')
    for finding in data:
        report_check(type(finding) is dict, 'finding_dict')
        report_check(required <= set(finding), 'finding_required_keys')
        report_check(set(finding) <= required | set(strings) | {'Entropy', 'Tags'},
                     'finding_extra_keys')
        # Verified presence remains unsupported, including false/null.
        commit = report_text(finding['Commit'], 40, REPORT_TEXT_CODES['Commit'])
        report_check(re.fullmatch('[0-9a-f]{40}', commit) is not None, 'finding_commit_hex')
        path = report_text(finding['File'], 4096, REPORT_TEXT_CODES['File'])
        rule = report_text(finding['RuleID'], 256, REPORT_TEXT_CODES['RuleID'])
        report_check(bool(path), 'finding_path_empty')
        report_check(not path.startswith('/'), 'finding_path_absolute')
        report_check('\\' not in path, 'finding_path_backslash')
        report_check(all(p not in ('', '.', '..') for p in path.split('/')), 'finding_path_components')
        report_check(bool(rule), 'finding_rule_empty')
        report_check(all(ord(c) >= 32 for c in path), 'finding_path_control')
        report_check(all(ord(c) >= 32 for c in rule), 'finding_rule_control')
        for key, codes in REPORT_POSITION_CODES.items():
            report_check(type(finding[key]) is int, codes[0])
            report_check(1 <= finding[key] <= 10**9, codes[1])
        report_check(finding['EndLine'] >= finding['StartLine'], 'finding_line_order')
        if finding['EndLine'] == finding['StartLine']:
            report_check(finding['EndColumn'] >= finding['StartColumn'], 'finding_column_order')
        fingerprint = report_text(finding['Fingerprint'], 8192, REPORT_TEXT_CODES['Fingerprint'])
        report_check(fingerprint == f"{commit}:{path}:{rule}:{finding['StartLine']}",
                     'finding_fingerprint_match')
        report_check(type(finding['Secret']) is str, 'finding_secret_type')
        report_check(finding['Secret'] == 'REDACTED', 'finding_secret_marker')
        match = report_text(finding['Match'], 65536, REPORT_TEXT_CODES['Match'])
        report_check('REDACTED' in match, 'finding_match_redaction')
        for key in strings:
            if key in finding:
                report_text(finding[key], LIMIT if key == 'Message' else 16384, REPORT_TEXT_CODES[key])
        if 'Entropy' in finding:
            entropy = finding['Entropy']
            report_check(type(entropy) in (int, float), 'finding_entropy_type')
            try:
                finite = math.isfinite(entropy)
            except OverflowError:
                raise DiagnosticFailure('finding_entropy_finite_check_overflow') from None
            report_check(finite, 'finding_entropy_finite')
            report_check(0 <= entropy <= 100, 'finding_entropy_range')
        if 'Tags' in finding:
            report_check(type(finding['Tags']) is list, 'finding_tags_list')
            report_check(len(finding['Tags']) <= 128, 'finding_tags_count')
            for tag in finding['Tags']:
                report_text(tag, 256, REPORT_TEXT_CODES['Tag'])
        occurrence = (commit, path, rule, finding['StartLine'], finding['EndLine'],
                      finding['StartColumn'], finding['EndColumn'])
        report_check(occurrence not in seen_occurrences, 'finding_duplicate_occurrence')
        seen_occurrences.add(occurrence)
        shape = [*occurrence, fingerprint, digest(match.encode('utf-8')), 'REDACTED', 'verified_absent']
        result.append({'finding': finding, 'fingerprint_sha256': digest(fingerprint.encode('utf-8')),
                       'shape_hash': digest(canonical(shape))})
    return result


def validate_manifest(raw,report_raw,summary_raw,rows):
    value=decode(raw)
    require(type(value)is dict and set(value)=={'artifact_schema','worker_execution_state','repository','run_id','trufflehog_capture_contract','generated_at','tools','partial_capture_tools','security_gate','human_review_required','client_delivery_allowed'})
    require(value['artifact_schema']==gate.VERSION and value['human_review_required']is True and value['client_delivery_allowed']is False)
    require(value['trufflehog_capture_contract']=='sanitized_v1')
    text(value['repository']);text(value['run_id']);text(value['generated_at'])
    tools=value['tools'];require(type(tools)is dict and set(tools)==gate.REQUIRED_TOOLS|{'eslint'})
    for record in tools.values():
        require(type(record)is dict)
        for key,item in record.items():
            if key in {'finding_count','blocking','needs_review','candidate_false_positive','diagnostic_count','error_count','warning_count'}or key.startswith('approved_'):
                require(integer(item))
        require(type(record.get('status'))is str)
    record=tools['gitleaks']
    required={'status','finding_count','artifact','artifact_hash','blocking','needs_review','approved_test_placeholders','approved_public_verifiers','triage','summary_artifact_hash'}
    require(required<=set(record)and set(record)<=required|{'approved_public_signing_fingerprints','approved_public_source_hashes'})
    require(record['status']=='completed'and record['artifact']==REPORT and record['artifact_hash']==digest(report_raw)and record['summary_artifact_hash']==digest(summary_raw))
    require(record['finding_count']==len(rows)and record['needs_review']==0)
    triage=record['triage'];require(type(triage)is list and len(triage)==len(rows))
    counts={name:0 for name in DISPOSITIONS}
    for row,item in zip(rows,triage):
        require(type(item)is dict and set(item)=={'fingerprint','file','line','rule_id','disposition'})
        finding=row['finding'];require(integer(item['line'])and item['line']==finding['StartLine'])
        require(item['fingerprint']==finding['Fingerprint']and item['file']==finding['File']and item['rule_id']==finding['RuleID'])
        require(type(item['disposition'])is str and item['disposition']in DISPOSITIONS)
        row['disposition']=item['disposition'];counts[item['disposition']]+=1
    for disposition,key in DISPOSITIONS.items():require(record.get(key,0)==counts[disposition])
    expected_gate={'scope':'blocking_risk_policy','status':'blocked'if gate.evaluate_gate(tools)else'passed',
        'blockers':gate.evaluate_gate(tools),'review_required':gate.evaluate_review_required(tools),
        'known_production_dependency_vulnerabilities_allowed':False,'missing_required_scanners_allowed':False,
        'untriaged_secret_findings_allowed':False,'high_confidence_workflow_injection_allowed':False}
    require(canonical(value['security_gate'])==canonical(expected_gate))
    require(value['worker_execution_state']==('failed'if expected_gate['status']=='blocked'else'completed'))
    require(value['partial_capture_tools']==sorted(k for k,v in tools.items()if v.get('capture_complete')is False))
    return value,counts


def git_bytes(root,args):
    # Bounded pipe capture: no unbounded temporary disk or retained stderr.
    process=subprocess.Popen(['git',*args],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    deadline=time.monotonic()+10
    try:
        chunks=[];size=0
        with selectors.DefaultSelector()as selector:
            selector.register(process.stdout,selectors.EVENT_READ)
            while True:
                remaining=deadline-time.monotonic();require(remaining>0)
                require(selector.select(remaining))
                chunk=os.read(process.stdout.fileno(),min(65536,LIMIT+1-size))
                if not chunk:break
                size+=len(chunk);require(size<=LIMIT);chunks.append(chunk)
        require(process.wait(timeout=max(0.001,deadline-time.monotonic()))==0)
        return b''.join(chunks)
    finally:
        process.stdout.close()
        if process.poll()is None:process.kill()
        process.wait(timeout=2)


def tool_digest(path):
    # Binary identity is streamed separately from the 4MiB JSON/metadata bound.
    require(path==path.resolve(strict=True));fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd);require(stat.S_ISREG(before.st_mode)and 0<before.st_size<=256*1024*1024)
        h=hashlib.sha256();total=0
        while True:
            chunk=os.read(fd,65536)
            if not chunk:break
            total+=len(chunk);require(total<=256*1024*1024);h.update(chunk)
        after=os.fstat(fd);require(total==before.st_size and (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns));return h.hexdigest()
    finally:os.close(fd)

