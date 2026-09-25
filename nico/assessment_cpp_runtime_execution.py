"""Execute and validate the frozen configure-first C/C++ runtime scope.

All assessed commands run inside the already-created disposable no-network
baseline container. The controller supplies only source-derived, release-owned
commands and bounded pinned corpus bytes.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import re
import time

from nico.assessment_worker_receipts import canonical_bytes
from nico.assessment_cpp_full_project_execution import READ_PROGRAM


LOG_EXEC_PROGRAM = r'''
import os, re, sys
log_path, argv = sys.argv[1], sys.argv[2:]
if (not argv or not re.fullmatch(r'/work/sanitize-(?:address|undefined)/nico-runtime-ctest.log', log_path)
        or os.path.basename(argv[0]) != 'ctest'):
    raise SystemExit(2)
fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
os.dup2(fd, 1); os.dup2(fd, 2)
if fd > 2: os.close(fd)
os.execvp(argv[0], argv)
'''

CORPUS_STAGE_PROGRAM = r'''
import base64, hashlib, json, os, pathlib, sys
raw = sys.stdin.buffer.read(1048577)
if len(raw) > 1048576 or os.getuid() != 0: raise SystemExit(2)
value = json.loads(raw)
rows = value.get('corpus')
if not isinstance(rows, list) or not 1 <= len(rows) <= 16: raise SystemExit(2)
replay = pathlib.Path('/work/runtime-corpus/connect_block')
campaign = pathlib.Path('/work/runtime-campaign/connect_block')
replay.mkdir(parents=True); campaign.mkdir(parents=True)
out = []
for index, row in enumerate(rows):
    data = base64.b64decode(row['base64'], validate=True)
    if hashlib.sha256(data).hexdigest() != row['sha256'] or len(data) != row['bytes']:
        raise SystemExit(2)
    a = replay / ('s' + str(index)); b = campaign / ('s' + str(index))
    a.write_bytes(data); b.write_bytes(data)
    a.chmod(0o444); b.chmod(0o644)
    out.append({'path':str(a),'sha256':row['sha256'],'bytes':len(data)})
replay.chmod(0o555)
campaign.chmod(0o777)
print(json.dumps(out, sort_keys=True))
'''


def _digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical_bytes(value)).hexdigest()


def _semantic_argv(argv):
    return list(argv)


def _run(observe, key, container, argv, *, seconds, limit=1024*1024, user=None,
         environment=None, workdir=None, data=None):
    prefix=['docker','exec']
    if user: prefix += ['--user='+user]
    if workdir: prefix += ['--workdir='+workdir]
    for name,value in sorted((environment or {}).items()):
        prefix += ['--env='+name+'='+value]
    if data is not None: prefix += ['--interactive']
    before=time.monotonic()
    response=observe(key,[*prefix,container,*argv],data=data,limit=limit,seconds=seconds)
    raw=response['output']
    return {'id':key,'argv':_semantic_argv(argv),'user':user,'environment':dict(sorted((environment or {}).items())),
        'workdir':workdir,'exit_code':response['exit_code'],'timed_out':response['timed_out'],
        'output_truncated':response['output_truncated'],'duration_ms':int((time.monotonic()-before)*1000),
        'output':base64.b64encode(raw).decode(),'output_sha256':hashlib.sha256(raw).hexdigest()}


def _ok(row):
    return row['exit_code']==0 and row['timed_out'] is False and row['output_truncated'] is False


def _output(row, maximum=1024*1024):
    try: raw=base64.b64decode(row['output'],validate=True)
    except (ValueError,TypeError) as exc: raise ValueError('worker_runtime_evidence_invalid') from exc
    if len(raw)>maximum or hashlib.sha256(raw).hexdigest()!=row['output_sha256']:
        raise ValueError('worker_runtime_evidence_invalid')
    return raw


def _read_file(observe, container, key, path, limit):
    row=_run(observe,key,container,['python3','-I','-S','-c',READ_PROGRAM,path,str(limit)],
        seconds=15,limit=limit*2+4096)
    if not _ok(row): raise ValueError('worker_runtime_artifact_unavailable')
    value=json.loads(_output(row,limit*2+4096))
    if not isinstance(value,dict) or set(value)!={'data','truncated'} or value['truncated'] is not False:
        raise ValueError('worker_runtime_artifact_unavailable')
    raw=base64.b64decode(value['data'],validate=True)
    if not 0 < len(raw) <= limit: raise ValueError('worker_runtime_artifact_unavailable')
    return row, raw


def _parse_functional_csv(raw, selected):
    """Bind exact membership independently of the runner's presentation order."""
    error = 'worker_runtime_functional_results_invalid'
    if (not isinstance(raw, bytes) or not isinstance(selected, list) or not selected
            or any(not isinstance(name, str) or not name or name == 'ALL' for name in selected)
            or len(selected) != len(set(selected))):
        raise ValueError(error)
    try:
        rows = list(csv.reader(io.StringIO(raw.decode('utf-8')), strict=True))
    except (UnicodeError, csv.Error) as exc:
        raise ValueError(error) from exc
    if (len(rows) < 3 or rows[0] != ['test', 'status', 'duration(seconds)']
            or any(len(row) != 3 for row in rows[1:])
            or rows[-1][0] != 'ALL'
            or any(re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', row[2]) is None for row in rows[1:])):
        raise ValueError(error)
    tests = rows[1:-1]
    names = [row[0] for row in tests]
    if (len(names) != len(selected) or len(set(names)) != len(names)
            or set(names) != set(selected)
            or any(row[1] not in {'Passed', 'Failed', 'Skipped'} for row in tests)):
        raise ValueError(error)
    by_name = {row[0]: row[1] for row in tests}
    total_status = 'Failed' if 'Failed' in by_name.values() else 'Passed'
    if rows[-1][1] != total_status:
        raise ValueError(error)
    return {'required': list(selected),
        'executed': [name for name in selected if by_name[name] != 'Skipped'],
        'passed': [name for name in selected if by_name[name] == 'Passed'],
        'failed': [name for name in selected if by_name[name] == 'Failed'],
        'skipped': [name for name in selected if by_name[name] == 'Skipped']}


def _discover(raw):
    value=json.loads(raw)
    rows=value.get('tests') if isinstance(value,dict) else None
    if not isinstance(rows,list) or not rows: raise ValueError('worker_runtime_sanitizer_discovery_invalid')
    names=[row.get('name') for row in rows]
    if any(not isinstance(name,str) or not name for name in names) or len(names)!=len(set(names)):
        raise ValueError('worker_runtime_sanitizer_discovery_invalid')
    return sorted(names)


def _junit(raw, required):
    from nico.assessment_cpp_full_project import _junit
    executed,passed,skipped=_junit(raw,required)
    return {'required':required,'executed':executed,'passed':passed,'skipped':skipped}


def _base_options(project_options):
    return ['-D'+k+'='+v for k,v in sorted(project_options.items())]


def _fuzz_campaign_metrics(row):
    if not _ok(row):
        return None
    try:
        text=_output(row,1024*1024).decode('utf-8',errors='replace')
    except ValueError:
        return None
    executed=re.search(r'stat::number_of_executed_units:\s*([0-9]+)',text)
    coverage=re.findall(r'\bcov:\s*([0-9]+)',text)
    if executed is None or not coverage:
        return None
    count=int(executed.group(1)); signal=int(coverage[-1])
    if count < 1 or signal < 0:
        return None
    return {'executions':count,'coverage_signal':signal,'duration_ms':row['duration_ms']}


def execute_runtime_plan(observe, container, plan, project_options):
    if (not callable(observe) or not isinstance(container,str) or not container
            or not isinstance(plan,dict) or plan.get('schema')!='nico.cpp-runtime-plan.v1'
            or plan.get('total_seconds')!=6000 or not isinstance(project_options,dict)):
        raise ValueError('worker_runtime_execution_contract_invalid')
    start=time.monotonic()
    deadline=start+plan['total_seconds']
    transport=observe
    def bounded_observe(key,argv,**kwargs):
        left=deadline-time.monotonic()
        if left<=0:
            raise ValueError('worker_runtime_deadline')
        requested=kwargs.get('seconds',15)
        kwargs['seconds']=max(0.001,min(requested,left))
        return transport(key,argv,**kwargs)
    observe=bounded_observe
    evidence={'schema':'nico.cpp-runtime-evidence.v1','plan_sha256':_digest(plan),
        'functional':None,'sanitizers':[],'fuzz':None,'complete':False,'error':None,'duration_ms':0}
    try:
        functional=plan['functional']; selected=list(functional['selected_tests'])
        setup=_run(observe,'runtime-functional-setup',container,
            ['python3','-I','-S','-c',"import pathlib; pathlib.Path('/work/functional-tests').mkdir(exist_ok=True)"],
            seconds=10)
        argv=['python3','/work/build/test/functional/test_runner.py','--jobs',str(functional['parallel']),
            '--quiet','--resultsfile=/work/build/nico-functional-results.csv',
            '--tmpdirprefix=/work/functional-tests',*selected]
        operation=_run(observe,'runtime-functional',container,argv,seconds=functional['seconds'],
            environment={'PYTHON_GIL':'1'},workdir='/work/build')
        results_read,results_raw=_read_file(observe,container,'runtime-functional-results',
            '/work/build/nico-functional-results.csv',1024*1024)
        summary=_parse_functional_csv(results_raw,selected)
        evidence['functional']={'setup':setup,'operation':operation,'results_read':results_read,'results':summary,
            'results_sha256':hashlib.sha256(results_raw).hexdigest()}
        if not (_ok(setup) and _ok(operation) and summary['passed']==selected and not summary['failed'] and not summary['skipped']):
            raise ValueError('worker_runtime_functional_failed')

        for kind in plan['sanitizers']['kinds']:
            directory='/work/sanitize-'+kind
            configure=['cmake','-S','/work/source','-B',directory,'-G','Unix Makefiles',
                '-DCMAKE_BUILD_TYPE=Debug','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
                '-DCMAKE_C_COMPILER=/usr/local/bin/gcc','-DCMAKE_CXX_COMPILER=/usr/local/bin/g++',
                *_base_options(project_options),'-DSANITIZERS='+kind]
            c=_run(observe,'runtime-'+kind+'-configure',container,configure,seconds=90)
            b=_run(observe,'runtime-'+kind+'-build',container,
                ['cmake','--build',directory,'--parallel',str(plan['sanitizers']['parallel'])],
                seconds=plan['sanitizers']['build_seconds'])
            d=_run(observe,'runtime-'+kind+'-discover',container,
                ['ctest','--test-dir',directory,'--show-only=json-v1'],seconds=60,limit=4*1024*1024)
            names=_discover(_output(d,4*1024*1024)) if _ok(d) else []
            log=directory+'/nico-runtime-ctest.log'; junit=directory+'/nico-runtime-junit.xml'
            env=({'ASAN_OPTIONS':'detect_leaks=0:halt_on_error=1'} if kind=='address'
                else {'UBSAN_OPTIONS':'halt_on_error=1'})
            if plan.get('unit_test_data') is not None:
                env['DIR_UNIT_TEST_DATA']='/work/unit_test_data'
            test_argv=['python3','-I','-S','-c',LOG_EXEC_PROGRAM,log,'ctest','--test-dir',directory,
                '--parallel',str(plan['sanitizers']['parallel']),'--timeout',
                str(plan['sanitizers']['test_case_seconds']),'--output-on-failure','--output-junit',junit]
            t=_run(observe,'runtime-'+kind+'-tests',container,test_argv,
                seconds=plan['sanitizers']['test_seconds'],environment=env)
            junit_read,junit_raw=_read_file(observe,container,'runtime-'+kind+'-junit',junit,4*1024*1024)
            summary=_junit(junit_raw,names)
            item={'kind':kind,'configure':c,'build':b,'discovery':d,'tests':t,'junit_read':junit_read,'results':summary,
                'junit_sha256':hashlib.sha256(junit_raw).hexdigest()}
            evidence['sanitizers'].append(item)
            if not (_ok(c) and _ok(b) and _ok(d) and _ok(t) and names
                    and summary['executed']==names and summary['passed']==names and not summary['skipped']):
                raise ValueError('worker_runtime_sanitizer_failed')

        fuzz=plan['fuzz']
        payload=canonical_bytes({'corpus':fuzz['corpus']})
        stage=_run(observe,'runtime-fuzz-corpus-stage',container,
            ['python3','-I','-S','-c',CORPUS_STAGE_PROGRAM],seconds=20,user='0:0',data=payload)
        staged=json.loads(_output(stage)) if _ok(stage) else []
        expected=[{'path':'/work/runtime-corpus/connect_block/s'+str(i),'sha256':row['sha256'],'bytes':row['bytes']}
                  for i,row in enumerate(fuzz['corpus'])]
        configure=['cmake','-S','/work/source','-B','/work/fuzz-build','-G','Unix Makefiles',
            '-DCMAKE_BUILD_TYPE=Debug','-DCMAKE_C_COMPILER=/usr/lib/llvm-17/bin/clang',
            '-DCMAKE_CXX_COMPILER=/usr/lib/llvm-17/bin/clang++','-DBUILD_FOR_FUZZING=ON',
            '-DSANITIZERS=address,fuzzer,undefined']
        fc=_run(observe,'runtime-fuzz-configure',container,configure,seconds=90)
        fb=_run(observe,'runtime-fuzz-build',container,
            ['cmake','--build','/work/fuzz-build','--parallel','1','--target',fuzz['build_target']],
            seconds=1200)
        fenv={'FUZZ':fuzz['target'],'ASAN_OPTIONS':'detect_leaks=0:halt_on_error=1',
              'UBSAN_OPTIONS':'halt_on_error=1'}
        replays=[]
        for i,row in enumerate(fuzz['corpus']):
            replays.append(_run(observe,'runtime-fuzz-replay-'+str(i),container,
                ['/work/fuzz-build/'+fuzz['binary'],'-runs='+str(fuzz['replay_runs']),
                 '/work/runtime-corpus/connect_block/s'+str(i)],seconds=60,environment=fenv))
        campaign=_run(observe,'runtime-fuzz-campaign',container,
            ['/work/fuzz-build/'+fuzz['binary'],'-runs='+str(fuzz['campaign_runs']),
             '-max_total_time='+str(fuzz['campaign_seconds']),'-print_final_stats=1','-seed=1','-max_len=4096',
             '/work/runtime-campaign/connect_block'],seconds=fuzz['campaign_seconds']+30,environment=fenv)
        campaign_metrics=_fuzz_campaign_metrics(campaign)
        evidence['fuzz']={'corpus_stage':stage,'staged':staged,'configure':fc,'build':fb,
            'replays':replays,'campaign':campaign,'campaign_metrics':campaign_metrics,'target':fuzz['target'],
            'corpus_sha256':[row['sha256'] for row in fuzz['corpus']]}
        if not (staged==expected and _ok(stage) and _ok(fc) and _ok(fb)
                and all(_ok(row) for row in replays) and _ok(campaign)):
            raise ValueError('worker_runtime_fuzz_failed')
        if campaign_metrics is None:
            raise ValueError('worker_runtime_fuzz_metrics_invalid')
        evidence['complete']=True
    except (ValueError,KeyError,TypeError,UnicodeError,json.JSONDecodeError) as exc:
        code=str(exc)
        evidence['error']=code if re.fullmatch(r'worker_runtime_[a-z_]+',code) else 'worker_runtime_failed'
    evidence['duration_ms']=int((time.monotonic()-start)*1000)
    return evidence


def _runtime_operation_specs(plan, project_options):
    """Reconstruct semantic commands; never execute worker-supplied argv."""
    specs = {}
    def add(key, argv, seconds, *, user=None, environment=None, workdir=None, limit=1024*1024):
        specs[key] = {'id': key, 'argv': argv, 'user': user,
            'environment': environment or {}, 'workdir': workdir,
            'seconds': seconds, 'limit': limit}
    def read(key, path, limit):
        add(key, ['python3', '-I', '-S', '-c', READ_PROGRAM, path, str(limit)],
            15, limit=limit*2+4096)
    functional = plan['functional']
    add('runtime-functional-setup', ['python3', '-I', '-S', '-c',
        "import pathlib; pathlib.Path('/work/functional-tests').mkdir(exist_ok=True)"], 10)
    add('runtime-functional', ['python3', '/work/build/test/functional/test_runner.py',
        '--jobs', str(functional['parallel']), '--quiet',
        '--resultsfile=/work/build/nico-functional-results.csv',
        '--tmpdirprefix=/work/functional-tests', *functional['selected_tests']],
        functional['seconds'], environment={'PYTHON_GIL': '1'}, workdir='/work/build')
    read('runtime-functional-results', '/work/build/nico-functional-results.csv', 1024*1024)
    for kind in plan['sanitizers']['kinds']:
        directory = '/work/sanitize-' + kind
        prefix = 'runtime-' + kind
        add(prefix+'-configure', ['cmake', '-S', '/work/source', '-B', directory,
            '-G', 'Unix Makefiles', '-DCMAKE_BUILD_TYPE=Debug', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
            '-DCMAKE_C_COMPILER=/usr/local/bin/gcc', '-DCMAKE_CXX_COMPILER=/usr/local/bin/g++',
            *_base_options(project_options), '-DSANITIZERS='+kind], 90)
        add(prefix+'-build', ['cmake', '--build', directory, '--parallel',
            str(plan['sanitizers']['parallel'])], plan['sanitizers']['build_seconds'])
        add(prefix+'-discover', ['ctest', '--test-dir', directory, '--show-only=json-v1'],
            60, limit=4*1024*1024)
        environment = ({'ASAN_OPTIONS': 'detect_leaks=0:halt_on_error=1'} if kind == 'address'
            else {'UBSAN_OPTIONS': 'halt_on_error=1'})
        if plan.get('unit_test_data') is not None:
            environment['DIR_UNIT_TEST_DATA'] = '/work/unit_test_data'
        add(prefix+'-tests', ['python3', '-I', '-S', '-c', LOG_EXEC_PROGRAM,
            directory+'/nico-runtime-ctest.log', 'ctest', '--test-dir', directory,
            '--parallel', str(plan['sanitizers']['parallel']), '--timeout',
            str(plan['sanitizers']['test_case_seconds']), '--output-on-failure',
            '--output-junit', directory+'/nico-runtime-junit.xml'],
            plan['sanitizers']['test_seconds'], environment=environment)
        read(prefix+'-junit', directory+'/nico-runtime-junit.xml', 4*1024*1024)
    fuzz = plan['fuzz']
    add('runtime-fuzz-corpus-stage', ['python3', '-I', '-S', '-c', CORPUS_STAGE_PROGRAM], 20, user='0:0')
    add('runtime-fuzz-configure', ['cmake', '-S', '/work/source', '-B', '/work/fuzz-build',
        '-G', 'Unix Makefiles', '-DCMAKE_BUILD_TYPE=Debug',
        '-DCMAKE_C_COMPILER=/usr/lib/llvm-17/bin/clang', '-DCMAKE_CXX_COMPILER=/usr/lib/llvm-17/bin/clang++',
        '-DBUILD_FOR_FUZZING=ON', '-DSANITIZERS=address,fuzzer,undefined'], 90)
    add('runtime-fuzz-build', ['cmake', '--build', '/work/fuzz-build', '--parallel', '1',
        '--target', fuzz['build_target']], 1200)
    environment = {'FUZZ': fuzz['target'], 'ASAN_OPTIONS': 'detect_leaks=0:halt_on_error=1',
        'UBSAN_OPTIONS': 'halt_on_error=1'}
    for index in range(len(fuzz['corpus'])):
        add('runtime-fuzz-replay-'+str(index), ['/work/fuzz-build/'+fuzz['binary'],
            '-runs='+str(fuzz['replay_runs']), '/work/runtime-corpus/connect_block/s'+str(index)],
            60, environment=environment)
    add('runtime-fuzz-campaign', ['/work/fuzz-build/'+fuzz['binary'], '-runs='+str(fuzz['campaign_runs']),
        '-max_total_time='+str(fuzz['campaign_seconds']), '-print_final_stats=1', '-seed=1', '-max_len=4096',
        '/work/runtime-campaign/connect_block'], fuzz['campaign_seconds']+30, environment=environment)
    return specs


def validate_runtime_evidence(evidence, plan, *, project_options=None):
    if (not isinstance(evidence,dict) or set(evidence)!={'schema','plan_sha256','functional','sanitizers','fuzz','complete','error','duration_ms'}
            or evidence.get('schema')!='nico.cpp-runtime-evidence.v1' or evidence.get('plan_sha256')!=_digest(plan)
            or plan.get('total_seconds')!=6000
            or type(evidence.get('complete')) is not bool or type(evidence.get('duration_ms')) is not int
            or not 0<=evidence['duration_ms']<=(plan['total_seconds']+5)*1000 or (evidence.get('error') is not None and
                (not isinstance(evidence['error'],str) or re.fullmatch(r'worker_runtime_[a-z_]+',evidence['error']) is None))):
        raise ValueError('worker_runtime_evidence_invalid')

    try:
        # Standalone legacy inspection can infer unbound project options. Real
        # probe/retained-artifact callers supply the release-bound option map.
        if project_options is None:
            arguments = evidence['sanitizers'][0]['configure']['argv'][11:-1]
            project_options = {}
            for argument in arguments:
                match = re.fullmatch(r'-D([A-Z][A-Z0-9_]{0,63})=([A-Za-z0-9_./+-]{1,120})', argument)
                if match is None or match[1] in project_options:
                    raise ValueError('worker_runtime_evidence_invalid')
                project_options[match[1]] = match[2]
        if not isinstance(project_options, dict):
            raise ValueError('worker_runtime_evidence_invalid')
        specs = _runtime_operation_specs(plan, project_options)
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise ValueError('worker_runtime_evidence_invalid') from exc
    seen = set()
    observed_duration_ms = 0

    operation_fields={'id','argv','user','environment','workdir','exit_code','timed_out',
        'output_truncated','duration_ms','output','output_sha256'}
    def operation(row, maximum=4*1024*1024):
        nonlocal observed_duration_ms
        if (not isinstance(row,dict) or set(row)!=operation_fields
                or not isinstance(row.get('id'),str) or not isinstance(row.get('argv'),list)
                or not isinstance(row.get('environment'),dict)
                or (row.get('user') is not None and not isinstance(row.get('user'),str))
                or (row.get('workdir') is not None and not isinstance(row.get('workdir'),str))
                or type(row.get('exit_code')) is not int or not -255 <= row['exit_code'] <= 255
                or type(row.get('timed_out')) is not bool or type(row.get('output_truncated')) is not bool
                or type(row.get('duration_ms')) is not int or row['duration_ms']<0):
            raise ValueError('worker_runtime_evidence_invalid')
        spec = specs.get(row['id'])
        if (spec is None or row['id'] in seen
                or any(row[key] != spec[key] for key in ('argv', 'user', 'environment', 'workdir'))
                or row['duration_ms'] > spec['seconds']*1000 + 2000):
            raise ValueError('worker_runtime_evidence_invalid')
        seen.add(row['id'])
        observed_duration_ms += row['duration_ms']
        if observed_duration_ms > evidence['duration_ms'] + 2:
            raise ValueError('worker_runtime_evidence_invalid')
        return _output(row, min(maximum, spec['limit']))

    def retained_file(row, limit):
        raw=operation(row,limit*2+4096)
        try: value=json.loads(raw)
        except (json.JSONDecodeError,UnicodeDecodeError) as exc:
            raise ValueError('worker_runtime_evidence_invalid') from exc
        if not isinstance(value,dict) or set(value)!={'data','truncated'} or value['truncated'] is not False:
            raise ValueError('worker_runtime_evidence_invalid')
        try: data=base64.b64decode(value['data'],validate=True)
        except (ValueError,TypeError) as exc:
            raise ValueError('worker_runtime_evidence_invalid') from exc
        if not 0 < len(data) <= limit:
            raise ValueError('worker_runtime_evidence_invalid')
        return data

    functional=evidence.get('functional')
    if (not isinstance(functional,dict)
            or set(functional)!={'setup','operation','results_read','results','results_sha256'}):
        raise ValueError('worker_runtime_evidence_invalid')
    operation(functional['setup']); operation(functional['operation'])
    functional_raw=retained_file(functional['results_read'],1024*1024)
    try: parsed_functional=_parse_functional_csv(functional_raw,plan['functional']['selected_tests'])
    except (ValueError,UnicodeError) as exc:
        raise ValueError('worker_runtime_evidence_invalid') from exc
    if (functional.get('results')!=parsed_functional
            or functional.get('results_sha256')!=hashlib.sha256(functional_raw).hexdigest()):
        raise ValueError('worker_runtime_evidence_invalid')

    sanitizers=evidence.get('sanitizers')
    if (not isinstance(sanitizers,list) or [row.get('kind') for row in sanitizers]!=plan['sanitizers']['kinds']):
        raise ValueError('worker_runtime_evidence_invalid')
    parsed_sanitizers=[]
    sanitizer_fields={'kind','configure','build','discovery','tests','junit_read','results','junit_sha256'}
    for row in sanitizers:
        if not isinstance(row,dict) or set(row)!=sanitizer_fields:
            raise ValueError('worker_runtime_evidence_invalid')
        for key in ('configure','build','discovery','tests'): operation(row[key])
        try: names=_discover(_output(row['discovery'],4*1024*1024))
        except (ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
            raise ValueError('worker_runtime_evidence_invalid') from exc
        junit_raw=retained_file(row['junit_read'],4*1024*1024)
        try: parsed=_junit(junit_raw,names)
        except ValueError as exc:
            raise ValueError('worker_runtime_evidence_invalid') from exc
        if row.get('results')!=parsed or row.get('junit_sha256')!=hashlib.sha256(junit_raw).hexdigest():
            raise ValueError('worker_runtime_evidence_invalid')
        parsed_sanitizers.append({'kind':row['kind'],**parsed})

    fuzz=evidence.get('fuzz')
    if (not isinstance(fuzz,dict) or set(fuzz)!={'corpus_stage','staged','configure','build','replays','campaign','campaign_metrics','target','corpus_sha256'}
            or fuzz.get('target')!=plan['fuzz']['target']
            or fuzz.get('corpus_sha256')!=[row['sha256'] for row in plan['fuzz']['corpus']]
            or not isinstance(fuzz.get('replays'),list)
            or len(fuzz['replays']) != len(plan['fuzz']['corpus'])):
        raise ValueError('worker_runtime_evidence_invalid')
    for key in ('corpus_stage','configure','build','campaign'): operation(fuzz[key])
    for row in fuzz['replays']: operation(row)
    try: staged=json.loads(_output(fuzz['corpus_stage']))
    except (json.JSONDecodeError,ValueError,UnicodeDecodeError) as exc:
        raise ValueError('worker_runtime_evidence_invalid') from exc
    expected=[{'path':'/work/runtime-corpus/connect_block/s'+str(i),'sha256':row['sha256'],'bytes':row['bytes']}
              for i,row in enumerate(plan['fuzz']['corpus'])]
    if staged!=expected or fuzz.get('staged')!=expected:
        raise ValueError('worker_runtime_evidence_invalid')
    parsed_metrics=_fuzz_campaign_metrics(fuzz['campaign'])
    if fuzz.get('campaign_metrics')!=parsed_metrics:
        raise ValueError('worker_runtime_evidence_invalid')

    if seen != set(specs):
        raise ValueError('worker_runtime_evidence_invalid')

    derived=(_ok(functional['setup']) and _ok(functional['operation'])
        and _ok(functional['results_read'])
        and parsed_functional['passed']==plan['functional']['selected_tests']
        and parsed_functional['executed']==plan['functional']['selected_tests']
        and not parsed_functional['failed'] and not parsed_functional['skipped']
        and all(_ok(row[k]) for row in sanitizers for k in ('configure','build','discovery','tests','junit_read'))
        and all(row['passed']==row['required'] and row['executed']==row['required'] and not row['skipped']
                for row in parsed_sanitizers)
        and _ok(fuzz['corpus_stage']) and _ok(fuzz['configure']) and _ok(fuzz['build'])
        and all(_ok(row) for row in fuzz['replays']) and _ok(fuzz['campaign']) and parsed_metrics is not None)
    if evidence['complete'] is not (derived and evidence['error'] is None):
        raise ValueError('worker_runtime_evidence_invalid')
    return {'complete':evidence['complete'],'functional':parsed_functional,
        'sanitizers':parsed_sanitizers,
        'fuzz':{'target':fuzz['target'],'replay_count':len(fuzz['replays']),
                'campaign_completed':_ok(fuzz['campaign']),'campaign_executions':(parsed_metrics or {}).get('executions'),
                'campaign_coverage_signal':(parsed_metrics or {}).get('coverage_signal'),
                'campaign_duration_ms':(parsed_metrics or {}).get('duration_ms'),
                'corpus_sha256':list(fuzz['corpus_sha256'])},
        'native_evidence_sha256':_digest(evidence)}
