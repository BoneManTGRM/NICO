"""Fresh, bounded identity-only diagnostic. Never changes scanner dispositions."""
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


def parse_findings(raw,summary_raw):
    data=decode(raw);summary=decode(summary_raw)
    require(type(data)is list and len(data)<=MAX_RECORDS-len(BINDINGS)-3)
    require(type(summary)is dict and set(summary)=={'scanner','status','finding_count','artifact_present','history_depth','exit_code'})
    require(summary['scanner']=='gitleaks'and summary['status']=='completed'and summary['artifact_present']is True and summary['history_depth']=='full')
    require(integer(summary['finding_count'])and summary['finding_count']==len(data))
    require(type(summary['exit_code'])is int and summary['exit_code']==(1 if data else 0))
    seen_occurrences=set();result=[]
    required={'Commit','File','RuleID','StartLine','EndLine','StartColumn','EndColumn','Fingerprint','Match','Secret'}
    strings={'Description','Author','Email','Date','Message','SymlinkFile','Link'}
    for finding in data:
        require(type(finding)is dict and required<=set(finding)and set(finding)<=required|strings|{'Entropy','Tags'})
        # Verified presence is deliberately unsupported, including false/null.
        commit=text(finding['Commit'],40);require(re.fullmatch('[0-9a-f]{40}',commit)is not None)
        path=text(finding['File'],4096);rule=text(finding['RuleID'],256)
        require(path and not path.startswith('/')and '\\'not in path and all(p not in ('','.','..')for p in path.split('/')))
        require(rule and all(ord(c)>=32 for c in path+rule))
        for key in ('StartLine','EndLine','StartColumn','EndColumn'):require(integer(finding[key],10**9)and finding[key]>0)
        require(finding['EndLine']>=finding['StartLine'])
        if finding['EndLine']==finding['StartLine']:require(finding['EndColumn']>=finding['StartColumn'])
        fingerprint=text(finding['Fingerprint'],8192)
        require(fingerprint==f"{commit}:{path}:{rule}:{finding['StartLine']}")
        require(finding['Secret']=='REDACTED'and type(finding['Secret'])is str)
        match=text(finding['Match'],65536);require('REDACTED'in match)
        for key in strings&set(finding):text(finding[key])
        if 'Entropy'in finding:require(type(finding['Entropy'])in(int,float)and math.isfinite(finding['Entropy'])and 0<=finding['Entropy']<=100)
        if 'Tags'in finding:
            require(type(finding['Tags'])is list and len(finding['Tags'])<=128)
            for tag in finding['Tags']:text(tag,256)
        occurrence=(commit,path,rule,finding['StartLine'],finding['EndLine'],finding['StartColumn'],finding['EndColumn'])
        require(occurrence not in seen_occurrences)
        seen_occurrences.add(occurrence)
        shape=[*occurrence,fingerprint,digest(match.encode('utf-8')),'REDACTED','verified_absent']
        result.append({'finding':finding,'fingerprint_sha256':digest(fingerprint.encode('utf-8')),'shape_hash':digest(canonical(shape))})
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


def capture_bindings(root,nonce):
    result={key:'unavailable'for key in BINDINGS};result['nonce']=nonce
    def attempt(key,callback):
        try:result[key]=callback()
        except Exception:result[key]='unavailable'
    def object_digest(ref):
        raw=git_bytes(root,['rev-parse','--verify',ref]).strip()
        require(re.fullmatch(b'[0-9a-f]{40}',raw)is not None)
        return digest(raw)
    for key,ref in [('head','HEAD'),('tree','HEAD^{tree}')]:
        attempt(key,lambda ref=ref:object_digest(ref))
    for key,env in [('pr_head','SECURITY_IDENTITY_PR_HEAD'),('base','SECURITY_IDENTITY_BASE')]:
        value=os.environ.get(env,'')
        if re.fullmatch('[0-9a-f]{40}',value):attempt(key,lambda value=value:object_digest(value+'^{commit}'))
    for key,env in [('run','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]:
        value=os.environ.get(env,'')
        if re.fullmatch('[0-9]{1,20}',value):result[key]=digest(value.encode())
    attempt('tool',lambda:tool_digest(Path(shutil.which('gitleaks')).absolute()))
    for key,path in [('config',root/'.gitleaks.toml'),('helper',Path(__file__).absolute()),('workflow',root/'.github/workflows/security-audit.yml'),('ignore',root/'.gitleaksignore'),('tool_policy',root/'scripts/install_hosted_scanner_binaries.py')]:
        attempt(key,lambda path=path:digest(read(path)))
    attempt('refset',lambda:digest(git_bytes(root,['for-each-ref','--sort=refname','--format=%(refname) %(objectname)'])))
    result['invocation']=digest(canonical(INVOKE))
    return result


def context_read(root):
    with stage('tracked_context'):
        require(not git_bytes(root,['ls-files','-z','--',CONTEXT]))
    with stage('context_read'):
        value=decode(read(root/CONTEXT))
    with stage('context_schema'):
        require(type(value)is dict and set(value)=={'schema','phase','bindings','artifacts'})
        require(value['schema']=='nico.security-identity-context.v1'and value['phase']in {'prepared','sealed'})
        require(type(value['bindings'])is dict and set(value['bindings'])==set(BINDINGS))
        require(all(sha(x)or x=='unavailable'for x in value['bindings'].values())and sha(value['bindings']['nonce']))
        require(type(value['artifacts'])is dict)
        require(set(value['artifacts'])==({REPORT,SUMMARY}if value['phase']=='sealed'else set()))
        require(all(sha(x)for x in value['artifacts'].values()))
    with stage('context_bindings'):
        require(capture_bindings(root,value['bindings']['nonce'])==value['bindings'])
    return value


def context_write(root,value):
    fd,name=tempfile.mkstemp(prefix='.security-identity-',dir=root)
    try:
        with os.fdopen(fd,'wb')as stream:stream.write(canonical(value)+b'\n')
        os.replace(name,root/CONTEXT)
    finally:
        if os.path.exists(name):os.unlink(name)


def prepare(root):
    # Refuse tracked sources; workflow freshness flags fence any pre-unlink failure.
    context = root / CONTEXT
    with stage('tracked_context'):
        require(not git_bytes(root, ['ls-files', '-z', '--', CONTEXT]))
    with stage('context_remove'):
        if context.exists() or context.is_symlink():
            context.unlink()
    with stage('tracked_outputs'):
        require(not git_bytes(root, ['ls-files', '-z', '--', REPORT, SUMMARY, MANIFEST]))
    with stage('outputs_remove'):
        for name in (REPORT, SUMMARY, MANIFEST):
            path = root / name
            if path.exists() or path.is_symlink():
                path.unlink()
    with stage('capture_bindings'):
        value = {'schema': 'nico.security-identity-context.v1', 'phase': 'prepared',
                 'bindings': capture_bindings(root, digest(secrets.token_bytes(32))), 'artifacts': {}}
    with stage('context_write'):
        context_write(root, value)


def seal(root):
    with stage('tracked_context'):
        require(not git_bytes(root, ['ls-files', '-z', '--', CONTEXT]))
    try:
        context = context_read(root)
    finally:
        with stage('context_remove'):
            path = root / CONTEXT
            if path.exists() or path.is_symlink():
                path.unlink()
    with stage('freshness_flag'):
        require(os.environ.get('SECURITY_IDENTITY_PREPARE_OK') == '1')
    with stage('context_phase'):
        require(context['phase'] == 'prepared')
    with stage('report_read'):
        report = read(root / REPORT)
    with stage('summary_read'):
        summary = read(root / SUMMARY)
    with stage('report_validation'):
        parse_findings(report, summary)
    context['artifacts'] = {REPORT: digest(report), SUMMARY: digest(summary)}
    context['phase'] = 'sealed'
    with stage('context_write'):
        context_write(root, context)


def emit(root):
    with stage('freshness_flag'):
        require(os.environ.get('SECURITY_IDENTITY_FRESH_CAPTURE') == 'true')
    context = context_read(root)
    with stage('context_phase'):
        require(context['phase'] == 'sealed')
    with stage('report_read'):
        report = read(root / REPORT)
    with stage('summary_read'):
        summary = read(root / SUMMARY)
    with stage('manifest_read'):
        manifest = read(root / MANIFEST)
    with stage('artifact_binding'):
        require(context['artifacts'] == {REPORT: digest(report), SUMMARY: digest(summary)})
    with stage('report_validation'):
        rows = parse_findings(report, summary)
    with stage('manifest_validation'):
        value, counts = validate_manifest(manifest, report, summary, rows)
    with stage('run_binding'):
        require(context['bindings']['run'] == digest(value['run_id'].encode()))
    with stage('output_bounds'):
        output=[{'schema':'nico.security-identity.v1','state':'observed','finding_count':len(rows),'blocking_count':counts['blocking'],
                 'gate':value['security_gate']['status'],'report_sha256':digest(report),'summary_sha256':digest(summary),'manifest_sha256':digest(manifest),'context_sha256':digest(canonical(context))}]
        output.append({'record':'counts',**counts,'identity_scope':'redacted_metadata','effective_config':'unverified'})
        output.extend({'record':'binding','key':key,'sha256':context['bindings'][key]}for key in BINDINGS)
        output.extend({'record':'finding','index':i,'fingerprint_sha256':row['fingerprint_sha256'],'shape_hash':row['shape_hash'],'disposition':row['disposition']}for i,row in enumerate(rows))
        lines=[canonical(row)+b'\n'for row in output]
        lines.append(canonical({'record':'end','records':len(lines),'output_sha256':digest(b''.join(lines))})+b'\n')
        require(len(lines)<=MAX_RECORDS and all(len(line)<=MAX_RECORD_BYTES for line in lines)and sum(map(len,lines))<=MAX_OUTPUT)
        return b''.join(lines)


def validate_console(raw):
    """Reject incomplete/reordered console transport; this does not authenticate it."""
    try:
        require(type(raw)is bytes and 0<len(raw)<=MAX_OUTPUT and raw.endswith(b'\n'))
        lines=raw.splitlines(keepends=True)
        require(3+len(BINDINGS)<=len(lines)<=MAX_RECORDS and all(len(x)<=MAX_RECORD_BYTES for x in lines))
        rows=[decode(x)for x in lines]
        end=rows[-1]
        require(type(end)is dict and set(end)=={'record','records','output_sha256'}and end['record']=='end')
        require(integer(end['records'])and end['records']==len(lines)-1 and end['output_sha256']==digest(b''.join(lines[:-1])))
        header=rows[0]
        require(type(header)is dict and set(header)=={'schema','state','finding_count','blocking_count','gate','report_sha256','summary_sha256','manifest_sha256','context_sha256'})
        require(header['schema']=='nico.security-identity.v1'and header['state']=='observed'and header['gate']in {'blocked','passed'})
        require(integer(header['finding_count'])and integer(header['blocking_count'])and header['blocking_count']<=header['finding_count'])
        require(all(sha(header[k])for k in ('report_sha256','summary_sha256','manifest_sha256','context_sha256')))
        counts=rows[1]
        require(type(counts)is dict and set(counts)=={'record','identity_scope','effective_config'}|set(DISPOSITIONS))
        require(counts['record']=='counts'and counts['identity_scope']=='redacted_metadata'and counts['effective_config']=='unverified')
        require(all(integer(counts[k])for k in DISPOSITIONS)and sum(counts[k]for k in DISPOSITIONS)==header['finding_count'])
        for key,row in zip(BINDINGS,rows[2:2+len(BINDINGS)]):
            require(type(row)is dict and set(row)=={'record','key','sha256'}and row['record']=='binding'and row['key']==key and (sha(row['sha256'])or row['sha256']=='unavailable'))
        findings=rows[2+len(BINDINGS):-1];require(len(findings)==header['finding_count'])
        shapes=set();observed_counts={k:0 for k in DISPOSITIONS}
        for index,row in enumerate(findings):
            require(type(row)is dict and set(row)=={'record','index','fingerprint_sha256','shape_hash','disposition'})
            require(row['record']=='finding'and integer(row['index'])and row['index']==index and sha(row['fingerprint_sha256'])and sha(row['shape_hash'])and row['disposition']in DISPOSITIONS)
            require(row['shape_hash']not in shapes)
            shapes.add(row['shape_hash']);observed_counts[row['disposition']]+=1
        require(observed_counts['blocking']==header['blocking_count']and all(observed_counts[k]==counts[k]for k in DISPOSITIONS))
        return True
    except Exception:return False


def write_output(raw):
    try:
        offset=0
        while offset<len(raw):
            written=os.write(1,raw[offset:])
            if not 0<written<=len(raw)-offset:return False
            offset+=written
        return True
    except Exception:return False


class QuietParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('invalid')


def main(argv=None):
    phase = 'cli'
    try:
        with stage('arguments'):
            command = QuietParser(add_help=False, exit_on_error=False)
            command.add_argument('action', choices=['prepare', 'seal', 'emit'])
            command.add_argument('--root', default='.')
            command.add_argument('--context', default=CONTEXT)
            args = command.parse_args(argv)
            require(args.context == CONTEXT)
        phase = args.action
        with stage('root'):
            root = Path(args.root).absolute()
            require(root == root.resolve(strict=True) and root.is_dir())
        if args.action == 'prepare':
            prepare(root)
            output = b''
        elif args.action == 'seal':
            seal(root)
            output = b''
        else:
            output = emit(root)
    except (Exception, SystemExit) as error:
        reason = error.reason if type(error) is DiagnosticFailure else 'unexpected'
        write_output(invalid_record(phase, reason))
        return 1
    return 0 if write_output(output) else 1


if __name__=='__main__':raise SystemExit(main())
