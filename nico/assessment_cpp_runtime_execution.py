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


# Fixed release-owned phase names, never paths supplied by assessed source.
# Descriptor-relative rmtree refuses top-level links and does not follow nested
# links. The outer disposable container remains responsible for final cleanup.
RECLAIM_PROGRAM = r'''
import json, os, shutil, stat, sys
PHASES = {'baseline': ('build', 'functional-tests'),
          'address': ('sanitize-address',), 'undefined': ('sanitize-undefined',)}

def reclaim(phase, *, root='/work'):
    if phase not in PHASES or not shutil.rmtree.avoids_symlink_attacks:
        raise ValueError('workspace_reclamation_policy')
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        device = os.fstat(fd).st_dev
        names = PHASES[phase]
        # Validate every top-level target before removing any of them.
        for name in names:
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode) or info.st_dev != device:
                raise ValueError('workspace_reclamation_target')
        def space():
            info = os.fstatvfs(fd)
            return {'capacity_bytes': info.f_blocks * info.f_frsize,
                    'available_bytes': info.f_bavail * info.f_frsize}
        before = space()
        for name in names:
            shutil.rmtree(name, dir_fd=fd)
        return {'phase': phase, 'removed': list(names), 'before': before, 'after': space()}
    finally:
        os.close(fd)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(2)
    print(json.dumps(reclaim(sys.argv[1]), sort_keys=True))
'''

_RECLAIM_PHASES = {'baseline': ['build', 'functional-tests'],
                   'address': ['sanitize-address'], 'undefined': ['sanitize-undefined']}


def _reclamation_result(raw, phase):
    error = 'worker_runtime_reclamation_failed'
    try:
        value = json.loads(raw)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError(error) from exc
    if (not isinstance(value, dict) or set(value) != {'phase', 'removed', 'before', 'after'}
            or value['phase'] != phase or value['removed'] != _RECLAIM_PHASES[phase]):
        raise ValueError(error)
    for key in ('before', 'after'):
        row = value[key]
        if (not isinstance(row, dict) or set(row) != {'capacity_bytes', 'available_bytes'}
                or any(type(v) is not int for v in row.values())
                or not 0 <= row['available_bytes'] <= row['capacity_bytes']
                or row['capacity_bytes'] <= 0):
            raise ValueError(error)
    if (value['before']['capacity_bytes'] != value['after']['capacity_bytes']
            or value['after']['available_bytes'] < value['before']['available_bytes']):
        raise ValueError(error)
    return value


def _reclaim(observe, container, evidence, phase):
    row = _run(observe, 'runtime-reclaim-'+phase, container,
        ['python3', '-I', '-S', '-c', RECLAIM_PROGRAM, phase], seconds=30, limit=4096)
    evidence['reclamations'].append(row)  # Retain failure before interpretation.
    if not _ok(row):
        raise ValueError('worker_runtime_reclamation_failed')
    _reclamation_result(_output(row, 4096), phase)


RUNTIME_RESOURCE_PROGRAM = r'''
import os, pathlib, re, json

def resources(*, work='/work', cgroup='/sys/fs/cgroup'):
    def read(name):
        try:
            with pathlib.Path(cgroup, name).open('r', encoding='ascii') as stream:
                raw = stream.read(4097)
            return raw if len(raw) <= 4096 else None
        except (OSError, UnicodeError):
            return None
    def number(name):
        raw = read(name)
        return int(raw.strip()) if raw is not None and re.fullmatch(r'[0-9]{1,20}', raw.strip()) else None
    raw = read('memory.events'); events = None
    if raw is not None:
        lines = [line.split() for line in raw.splitlines()]
        if (lines and all(len(row) == 2 and re.fullmatch(r'[a-z_]{1,40}', row[0])
                         and re.fullmatch(r'[0-9]{1,20}', row[1]) for row in lines)
                and len({row[0] for row in lines}) == len(lines)):
            events = {key:int(value) for key,value in lines}
    try:
        stat = os.statvfs(work)
        capacity, available = stat.f_blocks*stat.f_frsize, stat.f_bavail*stat.f_frsize
    except OSError:
        capacity = available = None
    return {'memory_current_bytes':number('memory.current'), 'memory_peak_bytes':number('memory.peak'),
            'memory_events':events, 'scratch_capacity_bytes':capacity, 'scratch_available_bytes':available}

if __name__ == '__main__':
    print(json.dumps(resources(), sort_keys=True))
'''


def _runtime_diagnostic_summary(log, resource, raw_log, raw_resource):
    error = 'worker_runtime_evidence_invalid'
    log_summary = {'state':'unavailable', 'output_sha256':log['output_sha256']}
    if _ok(log):
        try:
            value = json.loads(raw_log)
            if (not isinstance(value,dict) or set(value)!={'data','truncated'}
                    or type(value['truncated']) is not bool):
                raise ValueError(error)
            data = base64.b64decode(value['data'],validate=True)
            if len(data)>1024*1024:
                raise ValueError(error)
            log_summary.update(state='captured', bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(), truncated=value['truncated'])
        except (ValueError,TypeError,UnicodeError) as exc:
            raise ValueError(error) from exc
    resource_summary = None
    if _ok(resource):
        try:
            value = json.loads(raw_resource)
        except (ValueError,UnicodeError) as exc:
            raise ValueError(error) from exc
        fields = {'memory_current_bytes','memory_peak_bytes','memory_events',
                  'scratch_capacity_bytes','scratch_available_bytes'}
        if not isinstance(value,dict) or set(value)!=fields:
            raise ValueError(error)
        def valid_number(number):
            return number is None or (type(number) is int and 0<=number<2**64)
        if any(not valid_number(value[k]) for k in fields-{'memory_events'}):
            raise ValueError(error)
        events = value['memory_events']
        if events is not None and (not isinstance(events,dict) or len(events)>32
                or any(not isinstance(k,str) or re.fullmatch(r'[a-z_]{1,40}',k) is None
                    or type(v) is not int or not 0<=v<2**64 for k,v in events.items())):
            raise ValueError(error)
        capacity,available=value['scratch_capacity_bytes'],value['scratch_available_bytes']
        if (capacity is None) != (available is None) or (capacity is not None and available>capacity):
            raise ValueError(error)
        resource_summary = value
    return {'log':log_summary,'resources':resource_summary,
            'resource_output_sha256':resource['output_sha256']}


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


def _read_file(observe, container, key, path, limit, *, retain_row=None):
    row=_run(observe,key,container,['python3','-I','-S','-c',READ_PROGRAM,path,str(limit)],
        seconds=15,limit=limit*2+4096)
    if retain_row is not None:
        retain_row(row)  # Preserve a returned failure before interpreting its bytes.
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


def _completed_sanitizer_test_failure(operation, summary, junit_raw):
    """Recognize a completed CTest failure, never a timeout or missing test.

    This permits collection of independent later evidence; it does not turn the
    failed target test into successful qualification. Exact commands, retained
    bytes and population membership are validated separately by the caller.
    """
    from xml.etree import ElementTree as ET
    if (operation.get('exit_code') != 8 or operation.get('timed_out') is not False
            or operation.get('output_truncated') is not False
            or not summary.get('required') or summary.get('skipped')
            or summary.get('executed') != summary.get('required')
            or summary.get('passed') == summary.get('required')):
        return False
    if b'<!DOCTYPE' in junit_raw.upper() or b'<!ENTITY' in junit_raw.upper():
        return False
    try:
        root = ET.fromstring(junit_raw)
    except ET.ParseError:
        return False
    failed = set(summary['required']) - set(summary['passed'])
    failures = []
    for case in root.findall('testcase'):
        if case.get('name') not in failed:
            continue
        failure = case.find('failure')
        if (failure is None or failure.get('message') != 'Failed'
                or case.find('error') is not None or case.find('skipped') is not None
                or case.get('status', 'run') not in {'run', 'fail'}):
            return False
        failures.append(case.get('name'))
    return len(failures) == len(failed) and set(failures) == failed


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


def _sanitizer_test_parallel(plan):
    """Validate release-owned scheduling, preserving the historical plan."""
    policy = plan.get('schema') if isinstance(plan, dict) else None
    sanitizer = plan.get('sanitizers') if isinstance(plan, dict) else None
    if not isinstance(sanitizer, dict):
        raise ValueError('worker_runtime_scheduling_invalid')
    parallel = sanitizer.get('parallel')
    if type(parallel) is not int or not 1 <= parallel <= 4:
        raise ValueError('worker_runtime_scheduling_invalid')
    if policy == 'nico.cpp-runtime-plan.v1' and 'test_parallel' not in sanitizer:
        return parallel
    if (policy == 'nico.cpp-runtime-plan.v2'
            and type(sanitizer.get('test_parallel')) is int
            and sanitizer['test_parallel'] == min(2, parallel)):
        return sanitizer['test_parallel']
    raise ValueError('worker_runtime_scheduling_invalid')


def execute_runtime_plan(observe, container, plan, project_options, *, capture_failure_diagnostics=True):
    if (not callable(observe) or not isinstance(container,str) or not container
            or not isinstance(plan,dict) or plan.get('schema') not in ('nico.cpp-runtime-plan.v1','nico.cpp-runtime-plan.v2')
            or plan.get('total_seconds')!=6000 or not isinstance(project_options,dict)):
        raise ValueError('worker_runtime_execution_contract_invalid')
    test_parallel = _sanitizer_test_parallel(plan)
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
    if type(capture_failure_diagnostics) is not bool:
        raise ValueError('worker_runtime_diagnostic_contract_invalid')
    evidence={'schema':'nico.cpp-runtime-evidence.v4' if capture_failure_diagnostics else 'nico.cpp-runtime-evidence.v2','plan_sha256':_digest(plan),
        'functional':None,'sanitizers':[],'fuzz':None,'complete':False,'error':None,'duration_ms':0,
        'reclamations':[]}
    if capture_failure_diagnostics:
        evidence['failure_diagnostics'] = []
    completed_test_failure = False
    try:
        functional=plan['functional']; selected=list(functional['selected_tests'])
        retained={'setup':None,'operation':None,'results_read':None,'results':None,'results_sha256':None}
        evidence['functional']=retained
        setup=_run(observe,'runtime-functional-setup',container,
            ['python3','-I','-S','-c',"import pathlib; pathlib.Path('/work/functional-tests').mkdir(exist_ok=True)"],
            seconds=10)
        retained['setup']=setup
        if not _ok(setup):
            raise ValueError('worker_runtime_functional_failed')
        argv=['python3','/work/build/test/functional/test_runner.py','--jobs',str(functional['parallel']),
            '--quiet','--resultsfile=/work/build/nico-functional-results.csv',
            '--tmpdirprefix=/work/functional-tests',*selected]
        operation=_run(observe,'runtime-functional',container,argv,seconds=functional['seconds'],
            environment={'PYTHON_GIL':'1'},workdir='/work/build')
        retained['operation']=operation
        results_read,results_raw=_read_file(observe,container,'runtime-functional-results',
            '/work/build/nico-functional-results.csv',1024*1024,
            retain_row=lambda row: retained.update(results_read=row))
        summary=_parse_functional_csv(results_raw,selected)
        retained.update(results=summary,results_sha256=hashlib.sha256(results_raw).hexdigest())
        if not (_ok(setup) and _ok(operation) and summary['passed']==selected and not summary['failed'] and not summary['skipped']):
            raise ValueError('worker_runtime_functional_failed')

        _reclaim(observe, container, evidence, 'baseline')

        for kind in plan['sanitizers']['kinds']:
            directory='/work/sanitize-'+kind
            configure=['cmake','-S','/work/source','-B',directory,'-G','Unix Makefiles',
                '-DCMAKE_BUILD_TYPE=Debug','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
                '-DCMAKE_C_COMPILER=/usr/local/bin/gcc','-DCMAKE_CXX_COMPILER=/usr/local/bin/g++',
                *_base_options(project_options),'-DSANITIZERS='+kind]
            item={'kind':kind,'configure':None,'build':None,'discovery':None,'tests':None,
                'junit_read':None,'results':None,'junit_sha256':None}
            evidence['sanitizers'].append(item)
            c=_run(observe,'runtime-'+kind+'-configure',container,configure,seconds=90)
            item['configure']=c
            if not _ok(c):
                raise ValueError('worker_runtime_sanitizer_failed')
            b=_run(observe,'runtime-'+kind+'-build',container,
                ['cmake','--build',directory,'--parallel',str(plan['sanitizers']['parallel'])],
                seconds=plan['sanitizers']['build_seconds'])
            item['build']=b
            if not _ok(b):
                raise ValueError('worker_runtime_sanitizer_failed')
            d=_run(observe,'runtime-'+kind+'-discover',container,
                ['ctest','--test-dir',directory,'--show-only=json-v1'],seconds=60,limit=4*1024*1024)
            item['discovery']=d
            if not _ok(d):
                raise ValueError('worker_runtime_sanitizer_failed')
            names=_discover(_output(d,4*1024*1024))
            log=directory+'/nico-runtime-ctest.log'; junit=directory+'/nico-runtime-junit.xml'
            env=({'ASAN_OPTIONS':'detect_leaks=0:halt_on_error=1'} if kind=='address'
                else {'UBSAN_OPTIONS':'halt_on_error=1'})
            if plan.get('unit_test_data') is not None:
                env['DIR_UNIT_TEST_DATA']='/work/unit_test_data'
            test_argv=['python3','-I','-S','-c',LOG_EXEC_PROGRAM,log,'ctest','--test-dir',directory,
                '--parallel',str(test_parallel),'--timeout',
                str(plan['sanitizers']['test_case_seconds']),'--output-on-failure','--output-junit',junit]
            t=_run(observe,'runtime-'+kind+'-tests',container,test_argv,
                seconds=plan['sanitizers']['test_seconds'],environment=env)
            item['tests']=t
            if capture_failure_diagnostics and not _ok(t):
                # Capture the failed phase before a missing JUnit file can hide
                # progress or resource evidence. These reads do not grant test
                # completion; they retain bounded native diagnostic bytes.
                diagnostic = {'kind':kind, 'log_read':None, 'resources':None}
                evidence['failure_diagnostics'].append(diagnostic)
                diagnostic['log_read'] = _run(observe,'runtime-'+kind+'-test-log',container,
                    ['python3','-I','-S','-c',READ_PROGRAM,log,str(1024*1024)],
                    seconds=15,limit=2*1024*1024+4096)
                diagnostic['resources'] = _run(observe,'runtime-'+kind+'-resources',container,
                    ['python3','-I','-S','-c',RUNTIME_RESOURCE_PROGRAM],seconds=5,limit=4096)
            junit_read,junit_raw=_read_file(observe,container,'runtime-'+kind+'-junit',junit,4*1024*1024,
                retain_row=lambda row: item.update(junit_read=row))
            summary=_junit(junit_raw,names)
            item.update(junit_read=junit_read, results=summary,
                junit_sha256=hashlib.sha256(junit_raw).hexdigest())
            if not (_ok(c) and _ok(b) and _ok(d) and _ok(t) and names
                    and summary['executed']==names and summary['passed']==names and not summary['skipped']):
                if (capture_failure_diagnostics
                        and _completed_sanitizer_test_failure(t, summary, junit_raw)):
                    # The child process has exited and all required results are
                    # retained. Keep its failure, then collect independent stages.
                    completed_test_failure = True
                else:
                    raise ValueError('worker_runtime_sanitizer_failed')
            _reclaim(observe, container, evidence, kind)

        fuzz=plan['fuzz']
        payload=canonical_bytes({'corpus':fuzz['corpus']})
        stage=_run(observe,'runtime-fuzz-corpus-stage',container,
            ['python3','-I','-S','-c',CORPUS_STAGE_PROGRAM],seconds=20,user='0:0',data=payload)
        evidence['fuzz']={'corpus_stage':stage,'staged':None,'configure':None,'build':None,
            'replays':[],'campaign':None,'campaign_metrics':None,'target':fuzz['target'],
            'corpus_sha256':[row['sha256'] for row in fuzz['corpus']]}
        if not _ok(stage):
            raise ValueError('worker_runtime_fuzz_failed')
        staged=json.loads(_output(stage))
        evidence['fuzz']['staged']=staged
        expected=[{'path':'/work/runtime-corpus/connect_block/s'+str(i),'sha256':row['sha256'],'bytes':row['bytes']}
                  for i,row in enumerate(fuzz['corpus'])]
        if staged != expected:
            raise ValueError('worker_runtime_fuzz_failed')
        configure=['cmake','-S','/work/source','-B','/work/fuzz-build','-G','Unix Makefiles',
            '-DCMAKE_BUILD_TYPE=Debug','-DCMAKE_C_COMPILER=/usr/lib/llvm-17/bin/clang',
            '-DCMAKE_CXX_COMPILER=/usr/lib/llvm-17/bin/clang++','-DBUILD_FOR_FUZZING=ON',
            '-DSANITIZERS=address,fuzzer,undefined']
        fc=_run(observe,'runtime-fuzz-configure',container,configure,seconds=90)
        evidence['fuzz']['configure']=fc
        if not _ok(fc):
            raise ValueError('worker_runtime_fuzz_failed')
        fb=_run(observe,'runtime-fuzz-build',container,
            ['cmake','--build','/work/fuzz-build','--parallel','1','--target',fuzz['build_target']],
            seconds=1200)
        evidence['fuzz']['build']=fb
        if not _ok(fb):
            raise ValueError('worker_runtime_fuzz_failed')
        fenv={'FUZZ':fuzz['target'],'ASAN_OPTIONS':'detect_leaks=0:halt_on_error=1',
              'UBSAN_OPTIONS':'halt_on_error=1'}
        replays=evidence['fuzz']['replays']
        for i,row in enumerate(fuzz['corpus']):
            replays.append(_run(observe,'runtime-fuzz-replay-'+str(i),container,
                ['/work/fuzz-build/'+fuzz['binary'],'-runs='+str(fuzz['replay_runs']),
                 '/work/runtime-corpus/connect_block/s'+str(i)],seconds=60,environment=fenv))
            if not _ok(replays[-1]):
                raise ValueError('worker_runtime_fuzz_failed')
        campaign=_run(observe,'runtime-fuzz-campaign',container,
            ['/work/fuzz-build/'+fuzz['binary'],'-runs='+str(fuzz['campaign_runs']),
             '-max_total_time='+str(fuzz['campaign_seconds']),'-print_final_stats=1','-seed=1','-max_len=4096',
             '/work/runtime-campaign/connect_block'],seconds=fuzz['campaign_seconds']+30,environment=fenv)
        evidence['fuzz']['campaign']=campaign
        campaign_metrics=_fuzz_campaign_metrics(campaign)
        evidence['fuzz']={'corpus_stage':stage,'staged':staged,'configure':fc,'build':fb,
            'replays':replays,'campaign':campaign,'campaign_metrics':campaign_metrics,'target':fuzz['target'],
            'corpus_sha256':[row['sha256'] for row in fuzz['corpus']]}
        if not (staged==expected and _ok(stage) and _ok(fc) and _ok(fb)
                and all(_ok(row) for row in replays) and _ok(campaign)):
            raise ValueError('worker_runtime_fuzz_failed')
        if campaign_metrics is None:
            raise ValueError('worker_runtime_fuzz_metrics_invalid')
        evidence['complete']=not completed_test_failure
        if completed_test_failure:
            evidence['error']='worker_runtime_sanitizer_failed'
    except (ValueError,KeyError,TypeError,UnicodeError,json.JSONDecodeError) as exc:
        code=str(exc)
        evidence['error']=code if re.fullmatch(r'worker_runtime_[a-z_]+',code) else 'worker_runtime_failed'
    evidence['duration_ms']=int((time.monotonic()-start)*1000)
    return evidence


def _runtime_operation_specs(plan, project_options, *, failure_diagnostics=False):
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
            '--parallel', str(_sanitizer_test_parallel(plan)), '--timeout',
            str(plan['sanitizers']['test_case_seconds']), '--output-on-failure',
            '--output-junit', directory+'/nico-runtime-junit.xml'],
            plan['sanitizers']['test_seconds'], environment=environment)
        if failure_diagnostics:
            read(prefix+'-test-log', directory+'/nico-runtime-ctest.log', 1024*1024)
            add(prefix+'-resources', ['python3','-I','-S','-c',RUNTIME_RESOURCE_PROGRAM],5,limit=4096)
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



def _retained_file_bytes(raw, limit):
    """Decode an already envelope-checked native file read, not a summary."""
    error = 'worker_runtime_evidence_invalid'
    try:
        value = json.loads(raw)
        if (not isinstance(value, dict) or set(value) != {'data', 'truncated'}
                or value['truncated'] is not False):
            raise ValueError(error)
        data = base64.b64decode(value['data'], validate=True)
        if not 0 < len(data) <= limit:
            raise ValueError(error)
        return data
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError(error) from exc


def _validate_failed_functional_prefix(evidence, plan, operation):
    """Verify the returned functional failure; absent CSV means unknown results."""
    error='worker_runtime_evidence_invalid'
    def require(condition):
        if not condition:
            raise ValueError(error)
    require(evidence['complete'] is False and evidence['sanitizers']==[]
        and evidence['fuzz'] is None and evidence['reclamations']==[]
        and evidence.get('failure_diagnostics',[])==[])
    functional=evidence['functional']
    require(isinstance(functional,dict) and set(functional)==
        {'setup','operation','results_read','results','results_sha256'})
    def read(key,row):
        require(isinstance(row,dict) and row.get('id')==key)
        return operation(row,2*1024*1024+4096)
    setup=functional['setup']; read('runtime-functional-setup',setup)
    required=list(plan['functional']['selected_tests'])
    if not _ok(setup):
        require(all(functional[key] is None for key in ('operation','results_read','results','results_sha256'))
            and evidence['error']=='worker_runtime_functional_failed')
        failed='runtime-functional-setup'
        summary={'required':required,'executed':[],'passed':[],'failed':[],'skipped':[],'state':'not_executed'}
    else:
        runner=functional['operation']; read('runtime-functional',runner)
        results_read=functional['results_read']; returned=read('runtime-functional-results',results_read)
        if _ok(results_read):
            raw=_retained_file_bytes(returned,1024*1024)
            try:
                parsed=_parse_functional_csv(raw,required)
            except (ValueError,UnicodeError) as exc:
                raise ValueError(error) from exc
            require(functional['results']==parsed and functional['results_sha256']==hashlib.sha256(raw).hexdigest()
                and (not _ok(runner) or parsed['passed']!=required or parsed['executed']!=required
                     or bool(parsed['failed']) or bool(parsed['skipped']))
                and evidence['error']=='worker_runtime_functional_failed')
            summary=dict(parsed)
        else:
            require(functional['results'] is None and functional['results_sha256'] is None
                and evidence['error']=='worker_runtime_artifact_unavailable')
            summary={'required':required,'executed':None,'passed':None,'failed':None,'skipped':None}
        summary['state']='timed_out' if runner['timed_out'] else 'failed'
        # With valid CSV, a failed/skipped required test is a runner failure
        # even when its process incorrectly returned zero. Missing CSV is a
        # read failure only when the runner itself completed successfully.
        failed=('runtime-functional' if not _ok(runner) or _ok(results_read) else 'runtime-functional-results')
    return {'complete':False,'error':evidence['error'],'failure_operation':failed,'functional':summary,
        'sanitizers':[],'sanitizers_not_executed':list(plan['sanitizers']['kinds']),
        'fuzz':{'state':'not_executed','target':plan['fuzz']['target'],
            'required_replay_count':len(plan['fuzz']['corpus']), 'replay_count':0,
            'campaign_completed':False,'campaign_executions':None,'campaign_coverage_signal':None,
            'campaign_duration_ms':None,'corpus_sha256':[],
            'required_corpus_sha256':[row['sha256'] for row in plan['fuzz']['corpus']]},
        **({'failure_diagnostics':[]} if evidence['schema'] in {'nico.cpp-runtime-evidence.v3','nico.cpp-runtime-evidence.v4'} else {}),
        'native_evidence_sha256':_digest(evidence)}


def _validate_failed_runtime_prefix(evidence, plan, operation):
    """Reconstruct a corroborated v2 abort without inventing its missing suffix.

    Every present operation still passes the complete validator's exact command,
    identity, output-hash and timing checks. A prefix is accepted only with a
    native failure and no later execution except that test's result-file read.
    The returned record is explicitly incomplete and grants no completion credit.
    """
    if evidence['sanitizers']==[] and evidence['fuzz'] is None and evidence['reclamations']==[]:
        return _validate_failed_functional_prefix(evidence,plan,operation)
    error = 'worker_runtime_evidence_invalid'
    rows = {}; raw = {}; order = []
    def require(condition):
        if not condition:
            raise ValueError(error)
    def put(key, row):
        order.append(key)
        if row is None:
            return
        require(isinstance(row, dict) and row.get('id') == key and key not in rows)
        rows[key] = row
        raw[key] = operation(row, 8*1024*1024+4096)

    functional = evidence['functional']
    require(isinstance(functional, dict) and set(functional) ==
        {'setup','operation','results_read','results','results_sha256'})
    for field, suffix in (('setup','setup'), ('operation',''), ('results_read','results')):
        key = 'runtime-functional' + ('-'+suffix if suffix else '')
        put(key, functional[field])
    # The current v2 prefix starts after a fully retained functional stage.
    require(all(functional[k] is not None and _ok(functional[k])
                for k in ('setup','operation','results_read')))
    functional_raw = _retained_file_bytes(raw['runtime-functional-results'], 1024*1024)
    try:
        parsed_functional = _parse_functional_csv(functional_raw, plan['functional']['selected_tests'])
    except (ValueError, UnicodeError) as exc:
        raise ValueError(error) from exc
    require(functional['results'] == parsed_functional
        and functional['results_sha256'] == hashlib.sha256(functional_raw).hexdigest()
        and parsed_functional['passed'] == plan['functional']['selected_tests']
        and parsed_functional['executed'] == plan['functional']['selected_tests']
        and not parsed_functional['failed'] and not parsed_functional['skipped'])

    reclamations = evidence['reclamations']
    require(isinstance(reclamations, list) and len(reclamations) <= len(_RECLAIM_PHASES))
    reclamation_by_phase = {}
    for phase, row in zip(_RECLAIM_PHASES, reclamations):
        require(isinstance(row, dict) and row.get('id') == 'runtime-reclaim-'+phase)
        reclamation_by_phase[phase] = row
    def reclaim(phase):
        key = 'runtime-reclaim-'+phase
        row = reclamation_by_phase.get(phase)
        put(key, row)
        if row is not None and _ok(row):
            try:
                _reclamation_result(raw[key], phase)
            except ValueError as exc:
                raise ValueError(error) from exc
    reclaim('baseline')

    v4 = evidence['schema'] == 'nico.cpp-runtime-evidence.v4'
    v3 = evidence['schema'] in {'nico.cpp-runtime-evidence.v3','nico.cpp-runtime-evidence.v4'}
    continuable = set()
    diagnostics = evidence.get('failure_diagnostics', [])
    require(isinstance(diagnostics,list) and len(diagnostics)<=len(plan['sanitizers']['kinds']))
    diagnostic_by_kind = {}
    for value in diagnostics:
        require(isinstance(value,dict) and set(value)=={'kind','log_read','resources'}
            and value['kind'] in plan['sanitizers']['kinds'] and value['kind'] not in diagnostic_by_kind)
        diagnostic_by_kind[value['kind']] = value
    parsed_diagnostics = []
    sanitizers = evidence['sanitizers']; kinds = plan['sanitizers']['kinds']
    require(isinstance(sanitizers, list) and len(sanitizers) <= len(kinds)
        and all(isinstance(row, dict) for row in sanitizers)
        and [row.get('kind') for row in sanitizers] == kinds[:len(sanitizers)])
    parsed_sanitizers = []
    fields = {'kind','configure','build','discovery','tests','junit_read','results','junit_sha256'}
    native_fields = (('configure','configure'), ('build','build'), ('discovery','discover'),
                     ('tests','tests'), ('junit_read','junit'))
    for index, kind in enumerate(kinds):
        row = sanitizers[index] if index < len(sanitizers) else None
        if row is not None:
            require(set(row) == fields)
        prefix = 'runtime-'+kind
        failed_tests = row is not None and row['tests'] is not None and not _ok(row['tests'])
        require((kind in diagnostic_by_kind) is (v3 and failed_tests))
        for field, suffix in native_fields:
            put(prefix+'-'+suffix, row[field] if row is not None else None)
            if field == 'tests' and v3 and failed_tests:
                diagnostic = diagnostic_by_kind[kind]
                require(diagnostic['log_read'] is not None and diagnostic['resources'] is not None)
                put(prefix+'-test-log', diagnostic['log_read'])
                put(prefix+'-resources', diagnostic['resources'])
                parsed_diagnostics.append({'kind':kind, **_runtime_diagnostic_summary(
                    diagnostic['log_read'], diagnostic['resources'],raw[prefix+'-test-log'],raw[prefix+'-resources'])})
        if row is not None:
            require(row['configure'] is not None)
            names = None
            if row['discovery'] is not None and _ok(row['discovery']):
                try:
                    names = _discover(raw[prefix+'-discover'])
                except (ValueError, KeyError, TypeError) as exc:
                    raise ValueError(error) from exc
            results = None
            if row['junit_read'] is not None and _ok(row['junit_read']):
                require(names is not None and row['tests'] is not None)
                junit_raw = _retained_file_bytes(raw[prefix+'-junit'], 4*1024*1024)
                try:
                    results = _junit(junit_raw, names)
                except ValueError as exc:
                    raise ValueError(error) from exc
                require(row['results'] == results
                    and row['junit_sha256'] == hashlib.sha256(junit_raw).hexdigest())
                if v4 and _completed_sanitizer_test_failure(row['tests'], results, junit_raw):
                    continuable.add(prefix+'-tests')
            else:
                require(row['results'] is None and row['junit_sha256'] is None)
            timed_out = any(row[key] is not None and row[key]['timed_out']
                            for key, _ in native_fields)
            state = 'timed_out' if timed_out else 'failed'
            if results is not None:
                success = (all(row[k] is not None and _ok(row[k]) for k, _ in native_fields)
                    and results['passed'] == names and results['executed'] == names
                    and not results['skipped'])
                parsed_sanitizers.append({'kind':kind, 'state':'complete' if success else state, **results})
            else:
                parsed_sanitizers.append({'kind':kind, 'state':state, 'required':names,
                    'executed':None, 'passed':None, 'skipped':None})
        reclaim(kind)

    fuzz = evidence['fuzz']
    fuzz_fields = {'corpus_stage','staged','configure','build','replays','campaign',
                   'campaign_metrics','target','corpus_sha256'}
    if fuzz is not None:
        require(isinstance(fuzz, dict) and set(fuzz) == fuzz_fields
            and fuzz['target'] == plan['fuzz']['target']
            and fuzz['corpus_sha256'] == [r['sha256'] for r in plan['fuzz']['corpus']]
            and isinstance(fuzz['replays'],list)
            and len(fuzz['replays']) <= len(plan['fuzz']['corpus'])
            and fuzz['campaign'] is None and fuzz['campaign_metrics'] is None)
    for key, suffix in (('corpus_stage','corpus-stage'),('configure','configure'),('build','build')):
        put('runtime-fuzz-'+suffix, fuzz[key] if fuzz is not None else None)
    replays = fuzz['replays'] if fuzz is not None else []
    for index in range(len(plan['fuzz']['corpus'])):
        put('runtime-fuzz-replay-'+str(index), replays[index] if index < len(replays) else None)
    if fuzz is not None:
        require(fuzz['corpus_stage'] is not None)
        if _ok(fuzz['corpus_stage']):
            expected = [{'path':'/work/runtime-corpus/connect_block/s'+str(i),
                'sha256':row['sha256'],'bytes':row['bytes']} for i,row in enumerate(plan['fuzz']['corpus'])]
            try:
                staged = json.loads(raw['runtime-fuzz-corpus-stage'])
            except (ValueError, UnicodeError) as exc:
                raise ValueError(error) from exc
            require(staged == expected and fuzz['staged'] == expected)
        else:
            require(fuzz['staged'] is None)

    # Preserve every earlier failure. Only v4 may proceed after a fully
    # enumerated, non-timeout target-test failure; all other aborts stay terminal.
    for index, result in enumerate(parsed_sanitizers):
        if result['state'] != 'complete' and 'runtime-'+result['kind']+'-tests' not in continuable:
            require(index == len(parsed_sanitizers)-1 and fuzz is None
                and result['kind'] not in reclamation_by_phase)

    present = [key for key in order if key in rows]
    require(present == order[:len(present)])
    failures = [key for key in present if not _ok(rows[key])]
    nonfatal = set(continuable)
    for key in continuable:
        nonfatal.update((key.removesuffix('-tests')+'-test-log', key.removesuffix('-tests')+'-resources'))
    aborting = [key for key in failures if key not in nonfatal]
    # A budget exhausted between fuzz operations has no failed native command.
    # Accept only the real deadline code with elapsed-budget corroboration and
    # a contiguous, successful fuzz prefix; never invent the unstarted command.
    deadline_abort = (v4 and evidence['error'] == 'worker_runtime_deadline'
        and evidence['duration_ms'] >= plan['total_seconds']*1000
        and fuzz is not None and not aborting)
    require(bool(aborting) or deadline_abort)
    failed = aborting[0] if aborting else None
    after = present[present.index(failed)+1:] if failed is not None else []
    is_sanitizer_test = failed in {'runtime-'+kind+'-tests' for kind in kinds}
    test_prefix = failed.removesuffix('-tests') if failed is not None else ''
    diagnostic_suffix = [test_prefix+'-test-log',test_prefix+'-resources'] if v3 and is_sanitizer_test else []
    require((not after and not diagnostic_suffix) or (is_sanitizer_test
        and after in (diagnostic_suffix, diagnostic_suffix+[test_prefix+'-junit'])))
    junit_key = test_prefix+'-junit'

    if deadline_abort:
        expected_error = 'worker_runtime_deadline'
    elif failed.startswith('runtime-reclaim-'):
        expected_error = 'worker_runtime_reclamation_failed'
    elif failed.startswith('runtime-fuzz-'):
        expected_error = 'worker_runtime_fuzz_failed'
    elif failed.endswith('-junit') or (is_sanitizer_test and (junit_key not in rows or not _ok(rows[junit_key]))):
        expected_error = 'worker_runtime_artifact_unavailable'
    else:
        expected_error = 'worker_runtime_sanitizer_failed'
    require(evidence['error'] == expected_error)
    return {'complete':False, 'error':evidence['error'], 'failure_operation':failed,
        **({'first_failure_operation':failures[0] if failures else None} if v4 else {}),
        'functional':parsed_functional, 'sanitizers':parsed_sanitizers,
        'sanitizers_not_executed':kinds[len(sanitizers):],
        'fuzz':{'state':'not_executed' if fuzz is None else 'failed',
            'target':plan['fuzz']['target'],'required_replay_count':len(plan['fuzz']['corpus']),
            'replay_count':len(replays),'campaign_completed':False,'campaign_executions':None,
            'campaign_coverage_signal':None,'campaign_duration_ms':None,
            'corpus_sha256':[row['sha256'] for row in plan['fuzz']['corpus'][:len(replays)]],
            'required_corpus_sha256':[row['sha256'] for row in plan['fuzz']['corpus']]},
        **({'failure_diagnostics':parsed_diagnostics} if v3 else {}),
        'native_evidence_sha256':_digest(evidence)}

def validate_runtime_evidence(evidence, plan, *, project_options=None):
    v4 = isinstance(evidence, dict) and evidence.get('schema') == 'nico.cpp-runtime-evidence.v4'
    v3 = isinstance(evidence, dict) and evidence.get('schema') in {'nico.cpp-runtime-evidence.v3','nico.cpp-runtime-evidence.v4'}
    v2 = isinstance(evidence, dict) and evidence.get('schema') in {'nico.cpp-runtime-evidence.v2','nico.cpp-runtime-evidence.v3','nico.cpp-runtime-evidence.v4'}
    fields = {'schema','plan_sha256','functional','sanitizers','fuzz','complete','error','duration_ms'}
    if v2:
        fields.add('reclamations')
    if v3:
        fields.add('failure_diagnostics')
    if (not isinstance(evidence,dict) or set(evidence)!=fields
            or evidence.get('schema') not in {'nico.cpp-runtime-evidence.v1', 'nico.cpp-runtime-evidence.v2','nico.cpp-runtime-evidence.v3','nico.cpp-runtime-evidence.v4'}
            or evidence.get('plan_sha256')!=_digest(plan)
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
        specs = _runtime_operation_specs(plan, project_options, failure_diagnostics=v3)
        if v2:
            for phase in _RECLAIM_PHASES:
                specs['runtime-reclaim-'+phase] = {
                    'argv':['python3','-I','-S','-c',RECLAIM_PROGRAM,phase],
                    'seconds':30,'limit':4096,'user':None,'environment':{},'workdir':None}
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
        return _retained_file_bytes(operation(row, limit*2+4096), limit)

    if (v2 and evidence['complete'] is False and evidence['error'] is not None
            and (evidence['fuzz'] is None or (isinstance(evidence['fuzz'], dict)
                 and evidence['fuzz'].get('campaign') is None))):
        try:
            return _validate_failed_runtime_prefix(evidence, plan, operation)
        except (KeyError, TypeError, AttributeError, UnicodeError) as exc:
            raise ValueError('worker_runtime_evidence_invalid') from exc

    if v3 and not v4 and evidence['failure_diagnostics'] != []:
        raise ValueError('worker_runtime_evidence_invalid')

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
    completed_test_failures=[]
    parsed_diagnostics=[]
    diagnostic_by_kind={}
    if v4:
        diagnostics=evidence['failure_diagnostics']
        if not isinstance(diagnostics,list) or len(diagnostics)>len(plan['sanitizers']['kinds']):
            raise ValueError('worker_runtime_evidence_invalid')
        for diagnostic in diagnostics:
            if (not isinstance(diagnostic,dict) or set(diagnostic)!={'kind','log_read','resources'}
                    or diagnostic['kind'] not in plan['sanitizers']['kinds']
                    or diagnostic['kind'] in diagnostic_by_kind):
                raise ValueError('worker_runtime_evidence_invalid')
            diagnostic_by_kind[diagnostic['kind']]=diagnostic
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
        if v4:
            failed = not _ok(row['tests'])
            if (row['kind'] in diagnostic_by_kind) is not failed:
                raise ValueError('worker_runtime_evidence_invalid')
            if failed:
                if not _completed_sanitizer_test_failure(row['tests'],parsed,junit_raw):
                    raise ValueError('worker_runtime_evidence_invalid')
                diagnostic=diagnostic_by_kind[row['kind']]
                prefix='runtime-'+row['kind']
                if (not isinstance(diagnostic['log_read'],dict) or not isinstance(diagnostic['resources'],dict)
                        or diagnostic['log_read'].get('id')!=prefix+'-test-log'
                        or diagnostic['resources'].get('id')!=prefix+'-resources'):
                    raise ValueError('worker_runtime_evidence_invalid')
                raw_log=operation(diagnostic['log_read'],2*1024*1024+4096)
                raw_resource=operation(diagnostic['resources'],4096)
                parsed_diagnostics.append({'kind':row['kind'],**_runtime_diagnostic_summary(
                    diagnostic['log_read'],diagnostic['resources'],raw_log,raw_resource)})
                completed_test_failures.append(prefix+'-tests')
            if (not all(_ok(row[k]) for k in ('configure','build','discovery','junit_read'))
                    or parsed['executed']!=names or parsed['skipped']
                    or (not failed and parsed['passed']!=names)):
                raise ValueError('worker_runtime_evidence_invalid')
        parsed_sanitizers.append({'kind':row['kind'],**parsed,
            **({'state':'complete' if _ok(row['tests']) else 'failed'} if v4 else {})})

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

    if v2:
        rows = evidence['reclamations']
        if not isinstance(rows, list) or len(rows) != len(_RECLAIM_PHASES):
            raise ValueError('worker_runtime_evidence_invalid')
        for phase, row in zip(_RECLAIM_PHASES, rows):
            if not isinstance(row, dict) or row.get('id') != 'runtime-reclaim-'+phase:
                raise ValueError('worker_runtime_evidence_invalid')
            raw = operation(row, 4096)
            try:
                _reclamation_result(raw, phase)
            except ValueError as exc:
                raise ValueError('worker_runtime_evidence_invalid') from exc
            if not _ok(row):
                raise ValueError('worker_runtime_evidence_invalid')

    required_specs = {key for key in specs if not (v3 and key.endswith(('-test-log','-resources')))}
    if v4:
        required_specs |= {operation['id'] for diagnostic in diagnostic_by_kind.values()
                           for operation in (diagnostic['log_read'],diagnostic['resources'])}
    if seen != required_specs:
        raise ValueError('worker_runtime_evidence_invalid')
    if (v4 and completed_test_failures and all(_ok(fuzz[k]) for k in ('corpus_stage','configure','build','campaign'))
            and all(_ok(row) for row in fuzz['replays']) and parsed_metrics is not None
            and evidence['error']!='worker_runtime_sanitizer_failed'):
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
        **({'error':evidence['error'],
             'first_failure_operation':(completed_test_failures + [row['id']
                 for row in [*fuzz['replays'],fuzz['campaign']] if not _ok(row)]
                 + (['runtime-fuzz-campaign'] if parsed_metrics is None else []) + [None])[0],
             'failure_diagnostics':parsed_diagnostics} if v4 else {}),
        'sanitizers':parsed_sanitizers,
        'fuzz':{'target':fuzz['target'],'replay_count':len(fuzz['replays']),
                'campaign_completed':_ok(fuzz['campaign']),'campaign_executions':(parsed_metrics or {}).get('executions'),
                'campaign_coverage_signal':(parsed_metrics or {}).get('coverage_signal'),
                'campaign_duration_ms':(parsed_metrics or {}).get('duration_ms'),
                'corpus_sha256':list(fuzz['corpus_sha256'])},
        'native_evidence_sha256':_digest(evidence)}
