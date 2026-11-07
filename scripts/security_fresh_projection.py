"""Fresh bounded security projection with pinned Semgrep structural metadata."""
from __future__ import annotations
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile

try:
    from . import security_projection_common as common
    from . import security_source_dispositions as dispositions
    from . import security_semgrep_projection as semgrep_schema
except ImportError:
    import security_projection_common as common
    import security_source_dispositions as dispositions
    import security_semgrep_projection as semgrep_schema

TOOLS = ('gitleaks', 'semgrep')
REPORTS = {'gitleaks':'gitleaks.json','semgrep':'semgrep.json'}
CONTEXTS = {tool:'.security-projection-'+tool+'.json' for tool in TOOLS}
INVOCATIONS = {
    'gitleaks':['gitleaks','detect','--source','.','--report-format','json','--report-path','gitleaks.json','--no-banner','--redact'],
    'semgrep':['semgrep','scan','--config','auto','--json','--output','semgrep.json'],
}
BINDING_KEYS = ('head','tree','run','attempt','refset','helper','common','gate','disposition_helper',
                'approved_manifest','workflow','semgrep_schema','tool','invocation','requested_config')
PHASES = ('cli','prepare','capture','seal','emit')
REASONS = ('arguments','root','freshness','tracked_output','context','binding','report',
           'summary','manifest','semgrep','gitleaks_validation','exact_matcher','output_bounds','unexpected')
SCHEMA = 'nico.security-fresh-projection.v2'


class Invalid(ValueError):
    def __init__(self, reason):
        self.reason = reason if reason in REASONS else 'unexpected'
        super().__init__(self.reason)


def require(condition, reason):
    if not condition:
        raise Invalid(reason)


def invalid(phase, reason):
    return common.canonical({'schema':SCHEMA,'state':'invalid',
        'phase':phase if phase in PHASES else 'cli','reason':reason if reason in REASONS else 'unexpected'})+b'\n'


def untracked(root, names):
    require(not common.git_bytes(root,['ls-files','-z','--',*names]),'tracked_output')


def bindings(root, tool):
    result = {}
    for key, ref in [('head','HEAD'),('tree','HEAD^{tree}')]:
        raw=common.git_bytes(root,['rev-parse','--verify',ref]).strip()
        require(re.fullmatch(b'[0-9a-f]{40}',raw) is not None,'binding')
        result[key]=common.digest(raw)
    for key, env in [('run','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]:
        raw=os.environ.get(env,'')
        require(re.fullmatch('[0-9]{1,20}',raw) is not None,'binding')
        result[key]=common.digest(raw.encode())
    result['refset']=common.digest(common.git_bytes(root,['for-each-ref','--sort=refname','--format=%(refname) %(objectname)']))
    for key, path in [('helper',Path(__file__).absolute()),('common',Path(common.__file__).absolute()),
                      ('gate',Path(common.gate.__file__).absolute()),('disposition_helper',Path(dispositions.__file__).absolute()),
                      ('approved_manifest',dispositions.MANIFEST.absolute()),
                      ('workflow',root/'.github/workflows/security-audit.yml'),
                      ('semgrep_schema',Path(semgrep_schema.__file__).absolute())]:
        result[key]=common.digest(common.read(path))
    try:
        executable=shutil.which(tool)
        require(executable is not None,'binding')
        result['tool']=common.tool_digest(Path(executable).resolve(strict=True))
    except Exception:
        result['tool']='unavailable'
    result['invocation']=common.digest(common.canonical(INVOCATIONS[tool]))
    result['requested_config']=common.digest(b'auto') if tool=='semgrep' else 'unavailable'
    require(set(result)==set(BINDING_KEYS),'binding')
    return result


def write_context(root, tool, value):
    fd,name=tempfile.mkstemp(prefix='.security-projection-',dir=root)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(common.canonical(value)+b'\n')
        os.replace(name,root/CONTEXTS[tool])
    finally:
        if os.path.exists(name):os.unlink(name)


def read_context(root, tool):
    untracked(root,[CONTEXTS[tool]])
    value=common.decode(common.read(root/CONTEXTS[tool],4096))
    require(type(value)is dict and set(value)=={'schema','tool','phase','nonce','bindings','exit_code','report_sha256','summary_sha256'},'context')
    require(value['schema']==SCHEMA and value['tool']==tool and value['phase'] in ('prepared','captured','sealed'),'context')
    require(common.sha(value['nonce']) and value['bindings']==bindings(root,tool),'binding')
    require(all(common.sha(value[key])or value[key]=='unavailable'for key in ('report_sha256','summary_sha256')),'context')
    require(value['exit_code'] is None or type(value['exit_code'])is int and 0<=value['exit_code']<=255,'context')
    return value


def prepare(root, tool):
    names=[CONTEXTS[tool],REPORTS[tool]]+(['gitleaks-summary.json']if tool=='gitleaks'else ['scanner-worker-artifact.json'])
    untracked(root,names)
    # The workflow success flags fence failures before stale state removal.
    for name in names:
        path=root/name
        if path.exists()or path.is_symlink():path.unlink()
    require(not common.git_bytes(root,['status','--porcelain','--untracked-files=no']),'binding')
    value=dict(schema=SCHEMA,tool=tool,phase='prepared',nonce=common.digest(secrets.token_bytes(32)),
               bindings=bindings(root,tool),exit_code=None,report_sha256='unavailable',summary_sha256='unavailable')
    write_context(root,tool,value)


def capture(root, tool, exit_code):
    require(os.environ.get('SECURITY_PROJECTION_PREPARE_OK')=='1','freshness')
    value=read_context(root,tool)
    require(value['phase']=='prepared' and type(exit_code)is int and 0<=exit_code<=255,'context')
    value.update(phase='captured',exit_code=exit_code)
    # Capture before any existing fallback. Absent/oversized/invalid files are
    # not silently substituted with a fallback's later bytes.
    try:value['report_sha256']=common.digest(common.read(root/REPORTS[tool]))
    except Exception:value['report_sha256']='unavailable'
    write_context(root,tool,value)


def seal(root, tool):
    require(os.environ.get('SECURITY_PROJECTION_PREPARE_OK')=='1','freshness')
    require(os.environ.get('SECURITY_PROJECTION_CAPTURE_OK')=='1','freshness')
    value=read_context(root,tool)
    untracked(root,[CONTEXTS[tool]])
    (root/CONTEXTS[tool]).unlink()  # Failed sealing cannot leave an accepted old seal.
    require(value['phase']=='captured' and type(value['exit_code'])is int,'context')
    raw=common.read(root/REPORTS[tool])
    require(common.sha(value['report_sha256'])and common.digest(raw)==value['report_sha256'],'report')
    if tool=='gitleaks':
        summary=common.read(root/'gitleaks-summary.json')
        meta=common.decode(summary)
        require(type(meta)is dict and type(meta.get('exit_code'))is int and meta['exit_code']==value['exit_code'],'summary')
        value['summary_sha256']=common.digest(summary)
    value['phase']='sealed'
    write_context(root,tool,value)


def tracked_paths(root):
    """Bounded exact HEAD regular-blob names; no report-selected file is opened."""
    raw = common.git_bytes(root, ['ls-tree', '-r', '-z', 'HEAD'])
    names = set()
    for entry in raw.split(b'\0'):
        if not entry:
            continue
        metadata, name = entry.split(b'\t', 1)
        mode, kind, oid = metadata.split(b' ')
        require(re.fullmatch(b'[0-9a-f]{40}', oid) is not None, 'binding')
        if mode in (b'100644', b'100755') and kind == b'blob':
            names.add(name.decode('utf-8'))
    return frozenset(names)


def semgrep_projection(raw, manifest_record, tracked_paths=frozenset()):
    value=common.decode(raw)
    require(type(value)is dict and type(value.get('results'))is list and type(value.get('errors'))is list,'semgrep')
    results, errors=value['results'],value['errors']
    require(len(results)<=10000 and len(errors)<=2048,'semgrep')
    levels=Counter(dict(fatal=0,error=0,other=0,missing=0,invalid=0))
    malformed_errors=0
    for item in errors:
        if type(item)is not dict:
            malformed_errors+=1
            levels['invalid']+=1
        elif 'level' not in item:
            levels['missing']+=1
        elif type(item['level'])is not str:
            levels['invalid']+=1
        else:
            common.text(item['level'],256)
            level=item['level'].lower()
            levels[level if level in ('fatal','error')else'other']+=1
    dictionary_results=[item for item in results if type(item)is dict]
    # Exact existing gate policy, not a new Semgrep severity/category model.
    blocking=sum(str(item.get('check_id')or'unknown')in common.gate.SEMGREP_BLOCKING_RULES for item in dictionary_results)
    expected={'status':'failed'if levels['fatal']+levels['error']else'completed',
              'finding_count':len(results),'diagnostic_count':len(errors),
              'scanner_error_count':levels['fatal']+levels['error'],'capture_complete':not errors,
              'blocking':blocking,'needs_review':len(dictionary_results)-blocking}
    require(type(manifest_record)is dict and all(common.canonical(manifest_record.get(k))==common.canonical(v)for k,v in expected.items()),'manifest')
    require(manifest_record.get('artifact_hash')==common.digest(raw),'manifest')
    version=value.get('version')
    scanned = 'unavailable'
    paths = value.get('paths')
    if type(paths) is dict and 'scanned' in paths:
        candidates = paths['scanned']
        if type(candidates) is list and len(candidates) <= 10000:
            try:
                for path in candidates:
                    common.text(path, 16384)
                scanned = len(candidates)
            except Exception:
                pass

    return [
        {'record':'semgrep_counts','diagnostic_entries':len(errors),'dictionary_diagnostics':len(errors)-malformed_errors,
         'malformed_diagnostics':malformed_errors,'result_entries':len(results),'malformed_results':len(results)-len(dictionary_results),
         'policy_blocking_results':blocking,'policy_review_results':len(dictionary_results)-blocking},
        {'record':'semgrep_levels','basis':'existing_gate_level_policy',**levels},
        *semgrep_schema.project(errors, version, tracked_paths),
        {'record':'semgrep_coverage','scanned':scanned,'skipped':'unavailable','targets':'unavailable','rules':'unavailable',
         'resolved_configuration':'unavailable','basis':'existing_nico_consumer' if type(scanned) is int else 'unavailable'},
        {'record':'semgrep_version','reported':'matches_pinned_1_170_0'if type(version)is str and version=='1.170.0'else'unavailable',
         'expected':'1.170.0','package_identity':'unavailable'},
    ]


def frame(records):
    lines=[common.canonical(row)+b'\n'for row in records]
    lines.append(common.canonical({'record':'end','records':len(lines),'output_sha256':common.digest(b''.join(lines))})+b'\n')
    require(len(lines)<=128 and all(len(line)<=512 for line in lines)and sum(map(len,lines))<=65536,'output_bounds')
    return b''.join(lines)


def emit(root):
    require(all(os.environ.get('SECURITY_PROJECTION_'+tool.upper()+'_FRESH')=='true'for tool in TOOLS),'freshness')
    contexts={tool:read_context(root,tool)for tool in TOOLS}
    require(all(value['phase']=='sealed'for value in contexts.values()),'context')
    raw={tool:common.read(root/REPORTS[tool])for tool in TOOLS}
    require(all(common.digest(raw[tool])==contexts[tool]['report_sha256']for tool in TOOLS),'report')
    summary=common.read(root/'gitleaks-summary.json')
    require(common.digest(summary)==contexts['gitleaks']['summary_sha256'],'summary')
    try:rows=common.parse_findings(raw['gitleaks'],summary)
    except Exception:raise Invalid('gitleaks_validation') from None
    manifest_raw=common.read(root/'scanner-worker-artifact.json')
    manifest,counts=common.validate_manifest(manifest_raw,raw['gitleaks'],summary,rows)
    require(contexts['gitleaks']['bindings']['run']==common.digest(manifest['run_id'].encode()),'binding')
    common_keys=set(BINDING_KEYS)-{'tool','invocation','requested_config'}
    require(all(contexts['gitleaks']['bindings'][key]==contexts['semgrep']['bindings'][key]for key in common_keys),'binding')
    approved=dispositions._approved_bindings()
    exact=sum((row['fingerprint_sha256'],row['shape_hash'])in approved for row in rows)
    actual=dispositions.approved_indices(raw['gitleaks'],summary,common.decode(raw['gitleaks']),common.decode(summary))
    require(len(actual)==exact,'exact_matcher')
    require(all(rows[i]['disposition']=='approved_public_source_hash'for i in actual),'exact_matcher')
    records=[{'schema':SCHEMA,'state':'observed','finding_count':len(rows),'blocking_count':counts['blocking'],
              'gate':manifest['security_gate']['status'],'manifest_sha256':common.digest(manifest_raw)},
             {'record':'gitleaks_counts',**counts,'identity_scope':'redacted_metadata'},
             {'record':'exact_manifest','validation':'valid','matched_occurrences':exact,'approved_shapes':34,
              'sha256':dispositions.MANIFEST_SHA256,'hidden_value_authentication':False}]
    ordered_keys=[key for key in BINDING_KEYS if key in common_keys]
    for offset in range(0,len(ordered_keys),4):
        records.append({'record':'bindings','index':offset//4,
            **{key:contexts['gitleaks']['bindings'][key]for key in ordered_keys[offset:offset+4]}})
    for tool in TOOLS:
        value=contexts[tool]
        records.append({'record':'execution','tool':tool,'actual_exit':value['exit_code'],'report_sha256':value['report_sha256'],
            'context_sha256':common.digest(common.canonical(value)),'nonce_sha256':value['nonce']})
        records.append({'record':'tool_binding','tool':tool,'sha256':value['bindings']['tool'],
            'basis':'executable_bytes'if tool=='gitleaks'else'launcher_bytes_not_package',
            'invocation_sha256':value['bindings']['invocation'],'requested_config_sha256':value['bindings']['requested_config'],
            'effective_config':'unavailable'})
    records.extend({'record':'finding','index':i,'fingerprint_sha256':row['fingerprint_sha256'],
                    'shape_hash':row['shape_hash'],'disposition':row['disposition']}for i,row in enumerate(rows))
    records.extend(semgrep_projection(raw['semgrep'],manifest['tools']['semgrep'], tracked_paths(root)))
    output=frame(records)
    require(validate_console(output),'output_bounds')
    return output


def validate_console(raw):
    """Reject incomplete/reordered transport; hashes do not authenticate provenance."""
    try:
        require(type(raw)is bytes and 0<len(raw)<=65536 and raw.endswith(b'\n'),'output_bounds')
        lines=raw.splitlines(keepends=True)
        require(len(lines)<=128 and all(len(line)<=512 for line in lines),'output_bounds')
        rows=[common.decode(line)for line in lines]
        def exact(row, fields):
            require(type(row)is dict and set(row)==set(fields),'output_bounds')
        def number(value, upper=10**12):
            require(type(value)is int and 0<=value<=upper,'output_bounds')
        trailer=rows[-1];exact(trailer,('record','records','output_sha256'))
        number(trailer['records'],127)
        require(trailer=={'record':'end','records':len(rows)-1,'output_sha256':common.digest(b''.join(lines[:-1]))},'output_bounds')
        header=rows[0];exact(header,('schema','state','finding_count','blocking_count','gate','manifest_sha256'))
        require(header['schema']==SCHEMA and header['state']=='observed'and header['gate']in ('passed','blocked')and common.sha(header['manifest_sha256']),'output_bounds')
        number(header['finding_count'],110);number(header['blocking_count'],header['finding_count'])
        require(len(rows)>=header['finding_count']+18,'output_bounds')
        counts=rows[1];exact(counts,{'record','identity_scope'}|set(common.DISPOSITIONS))
        require(counts['record']=='gitleaks_counts'and counts['identity_scope']=='redacted_metadata','output_bounds')
        for key in common.DISPOSITIONS:number(counts[key])
        require(sum(counts[key]for key in common.DISPOSITIONS)==header['finding_count']and counts['blocking']==header['blocking_count'],'output_bounds')
        matcher=rows[2];exact(matcher,('record','validation','matched_occurrences','approved_shapes','sha256','hidden_value_authentication'))
        require(matcher['record']=='exact_manifest'and matcher['validation']=='valid'and type(matcher['approved_shapes'])is int and matcher['approved_shapes']==34 and matcher['sha256']==dispositions.MANIFEST_SHA256 and matcher['hidden_value_authentication']is False,'output_bounds')
        number(matcher['matched_occurrences'],min(34,header['finding_count']))
        require(matcher['matched_occurrences']<=counts['approved_public_source_hash'],'output_bounds')
        common_keys=[key for key in BINDING_KEYS if key not in ('tool','invocation','requested_config')]
        position=3
        for offset in range(0,len(common_keys),4):
            row=rows[position];position+=1
            keys=common_keys[offset:offset+4];exact(row,{'record','index',*keys})
            require(row['record']=='bindings'and type(row['index'])is int and row['index']==offset//4 and all(common.sha(row[key])for key in keys),'output_bounds')
        for tool in TOOLS:
            row=rows[position];position+=1
            exact(row,('record','tool','actual_exit','report_sha256','context_sha256','nonce_sha256'))
            require(row['record']=='execution'and row['tool']==tool and all(common.sha(row[key])for key in ('report_sha256','context_sha256','nonce_sha256')),'output_bounds')
            number(row['actual_exit'],255)
            row=rows[position];position+=1
            exact(row,('record','tool','sha256','basis','invocation_sha256','requested_config_sha256','effective_config'))
            require(row['record']=='tool_binding'and row['tool']==tool and (common.sha(row['sha256'])or row['sha256']=='unavailable')and row['basis']==('executable_bytes'if tool=='gitleaks'else'launcher_bytes_not_package')and row['effective_config']=='unavailable','output_bounds')
            require(row['invocation_sha256']==common.digest(common.canonical(INVOCATIONS[tool]))and row['requested_config_sha256']==(common.digest(b'auto')if tool=='semgrep'else'unavailable'),'output_bounds')
        shapes=set();actual=Counter({key:0 for key in common.DISPOSITIONS})
        for index in range(header['finding_count']):
            row=rows[position];position+=1
            exact(row,('record','index','fingerprint_sha256','shape_hash','disposition'))
            require(row['record']=='finding'and type(row['index'])is int and row['index']==index and common.sha(row['fingerprint_sha256'])and common.sha(row['shape_hash'])and row['disposition']in common.DISPOSITIONS and row['shape_hash']not in shapes,'output_bounds')
            shapes.add(row['shape_hash']);actual[row['disposition']]+=1
        require(all(actual[key]==counts[key]for key in actual),'output_bounds')
        row=rows[position];position+=1
        count_keys=('diagnostic_entries','dictionary_diagnostics','malformed_diagnostics','result_entries','malformed_results','policy_blocking_results','policy_review_results')
        exact(row,{'record',*count_keys});require(row['record']=='semgrep_counts','output_bounds')
        for key in count_keys:number(row[key],2048 if key.endswith('diagnostics')or key=='diagnostic_entries'else 10000)
        require(row['dictionary_diagnostics']+row['malformed_diagnostics']==row['diagnostic_entries']and row['malformed_results']+row['policy_blocking_results']+row['policy_review_results']==row['result_entries'],'output_bounds')
        diagnostics=row['diagnostic_entries']
        row=rows[position];position+=1;level_keys=('fatal','error','other','missing','invalid')
        exact(row,{'record','basis',*level_keys})
        require(row['record']=='semgrep_levels'and row['basis']=='existing_gate_level_policy','output_bounds')
        for key in level_keys:number(row[key],2048)
        require(sum(row[key]for key in level_keys)==diagnostics,'output_bounds')
        row=rows[position];position+=1
        exact(row,{'record','mapping','schema_sha256','recognized_entries',*semgrep_schema.CATEGORIES})
        require(row['record']=='semgrep_categories' and row['mapping']=='pinned_1_170_0' and row['schema_sha256']==semgrep_schema.SCHEMA_SHA256,'output_bounds')
        for key in (*semgrep_schema.CATEGORIES,'recognized_entries'):number(row[key],diagnostics)
        require(sum(row[key]for key in semgrep_schema.CATEGORIES)==diagnostics,'output_bounds')
        require(diagnostics-row['unknown']<=row['recognized_entries'],'output_bounds')
        category_counts=row
        row=rows[position];position+=1
        exact(row,{'record','basis',*semgrep_schema.SEVERITIES})
        require(row['record']=='semgrep_severities' and row['basis']=='pinned_error_severity','output_bounds')
        for key in semgrep_schema.SEVERITIES:number(row[key],diagnostics)
        require(sum(row[key]for key in semgrep_schema.SEVERITIES)==diagnostics,'output_bounds')
        severity_counts=row
        row=rows[position];position+=1
        exact(row,('record','state','reported_entries','grouped_entries','ungrouped_entries','group_count','semantic_deduplication','path_binding'))
        require(row['record']=='semgrep_groups' and row['state']=='structural_metadata' and row['semantic_deduplication']is False and row['path_binding']=='head_regular_blob_membership','output_bounds')
        for key in ('reported_entries','grouped_entries','ungrouped_entries','group_count'):number(row[key],diagnostics)
        require(row['reported_entries']==diagnostics and row['grouped_entries']+row['ungrouped_entries']==diagnostics,'output_bounds')
        require(row['grouped_entries']<=category_counts['recognized_entries'],'output_bounds')
        require(len(rows)==header['finding_count']+18+row['group_count'],'output_bounds')
        group_count=row['group_count'];grouped=row['grouped_entries'];total=0
        group_categories=Counter();group_severities=Counter();last=''
        for index in range(group_count):
            row=rows[position];position+=1
            exact(row,('record','index','shape_sha256','category','severity','occurrences'))
            require(row['record']=='semgrep_group' and type(row['index'])is int and row['index']==index and common.sha(row['shape_sha256']) and row['shape_sha256']>last,'output_bounds')
            require(row['category']in semgrep_schema.CATEGORIES and row['severity']in ('error','warning','info'),'output_bounds')
            number(row['occurrences'],diagnostics);require(row['occurrences']>0,'output_bounds')
            total+=row['occurrences'];group_categories[row['category']]+=row['occurrences'];group_severities[row['severity']]+=row['occurrences'];last=row['shape_sha256']
        require(total==grouped and all(count<=category_counts[key]for key,count in group_categories.items()) and all(count<=severity_counts[key]for key,count in group_severities.items()),'output_bounds')
        coverage=rows[position];position+=1
        exact(coverage,('record','scanned','skipped','targets','rules','resolved_configuration','basis'))
        scanned=coverage['scanned']
        if scanned != 'unavailable':number(scanned,10000)
        require(coverage=={'record':'semgrep_coverage','scanned':scanned,'skipped':'unavailable','targets':'unavailable','rules':'unavailable','resolved_configuration':'unavailable','basis':'existing_nico_consumer' if type(scanned)is int else 'unavailable'},'output_bounds')
        row=rows[position];exact(row,('record','reported','expected','package_identity'))
        require(row['record']=='semgrep_version'and row['reported']in ('matches_pinned_1_170_0','unavailable')and row['expected']=='1.170.0'and row['package_identity']=='unavailable','output_bounds')
        if row['reported']=='unavailable':
            require(category_counts['recognized_entries']==0 and grouped==0 and all(severity_counts[key]==0 for key in ('error','warning','info')),'output_bounds')
        return True
    except Exception:return False


def write_output(raw):
    try:
        while raw:
            size=os.write(1,raw)
            if size<=0:return False
            raw=raw[size:]
        return True
    except OSError:return False


class QuietParser(argparse.ArgumentParser):
    def error(self, message):
        raise Invalid('arguments')


def main(argv=None):
    phase='cli'
    try:
        parser=QuietParser(add_help=False)
        parser.add_argument('action',choices=PHASES[1:])
        parser.add_argument('--tool',choices=TOOLS)
        parser.add_argument('--root',default='.')
        parser.add_argument('--exit-code',type=int)
        args=parser.parse_args(argv);phase=args.action
        require((args.tool is not None)==(phase!='emit'),'arguments')
        require((args.exit_code is not None)==(phase=='capture'),'arguments')
        root=Path(args.root).absolute()
        require(root==root.resolve(strict=True)and root.is_dir(),'root')
        if phase=='prepare':prepare(root,args.tool);output=b''
        elif phase=='capture':capture(root,args.tool,args.exit_code);output=b''
        elif phase=='seal':seal(root,args.tool);output=b''
        else:output=emit(root)
    except (Exception,SystemExit) as error:
        output=invalid(phase,error.reason if type(error)is Invalid else'unexpected')
        write_output(output)
        return 1
    return 0 if write_output(output)else 1


if __name__=='__main__':raise SystemExit(main())
