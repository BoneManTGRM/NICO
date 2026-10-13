"""Diagnostic-only isolated replays of retained timeout cases.

This tool never publishes a worker receipt or activates a production profile.
Source/target identity and historical evidence are verified before any native
operation. Every assessed command uses the existing disposable container policy.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import textwrap
import time
import zipfile
from uuid import uuid4

from nico.assessment_worker_receipts import canonical_bytes

MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_UNPACKED_BYTES = 192 * 1024 * 1024


def isolated_ctest_argv(names, name, seconds):
    if (not isinstance(names, list) or not names
            or any(not isinstance(n, str) or not n or len(n) > 200
                   or any(ord(c) < 32 for c in n) for n in names)
            or len(names) != len(set(names))
            or name not in names or type(seconds) is not int or not 1 <= seconds <= 300):
        raise ValueError('diagnostic_test_selection_invalid')
    return ['ctest', '--test-dir', '/work/sanitize-address', '--parallel', '1',
            '--timeout', str(seconds), '--output-on-failure', '--output-junit',
            '/work/sanitize-address/nico-diagnostic-junit.xml', '-R', '^' + re.escape(name) + '$']


def metrics_delta(before, after):
    result = {}
    for field in ('cpu', 'memory_events'):
        a, b = before.get(field), after.get(field)
        if (not isinstance(a, dict) or not isinstance(b, dict) or set(a) != set(b)
                or any(type(a[k]) is not int or type(b[k]) is not int or not 0 <= a[k] <= b[k]
                       for k in a)):
            result[field] = None
        else:
            result[field] = {k: b[k] - a[k] for k in a}
    return result


def provision_script(workflow, step_name):
    """Reuse one trusted exact-source recipe, not a second toolchain definition."""
    marker = '  project-baseline-qualification:\n'
    if workflow.count(marker) != 1:
        raise ValueError('diagnostic_recipe_job_invalid')
    job = workflow.split(marker, 1)[1]
    match = re.search(r'^  [A-Za-z0-9_-]+:\s*$', job, re.M)
    if match:
        job = job[:match.start()]
    step = '      - name: ' + step_name + '\n'
    if job.count(step) != 1:
        raise ValueError('diagnostic_recipe_step_invalid')
    body = job.split(step, 1)[1]
    # A literal step ID names retained outputs; it does not change the recipe.
    header = re.match(r'(?:        id: [A-Za-z_][A-Za-z0-9_-]*\n)?        run: \|\n', body)
    if header is None:
        raise ValueError('diagnostic_recipe_step_invalid')
    body = body[header.end():]
    lines = []
    for line in body.splitlines():
        if line and not line.startswith('          '):
            break
        lines.append(line[10:] if line else '')
    script = '\n'.join(lines).strip() + '\n'
    if not script.strip() or '${{' in script:
        raise ValueError('diagnostic_recipe_interpolation_unsupported')
    return script


def isolated_fallback_request(request, context_id):
    """One diagnostic selection; original hashes, limits and populations survive."""
    from copy import deepcopy
    from nico.assessment_cpp_clang_fallback import _request_limits
    _request_limits(request)
    contexts = [row for row in request['contexts'] if row['context_id'] == context_id]
    if len(contexts) != 1:
        raise ValueError('diagnostic_context_selection_invalid')
    selected = deepcopy(request)
    selected['contexts'] = deepcopy(contexts)
    return selected


def diagnostic_status(runtime, static, boundary, cleanup):
    return {'status': 'ISOLATED_CASES_COMPLETED' if all(v is True for v in
            (runtime, static, boundary, cleanup)) else 'INCOMPLETE',
            'production_qualified': False, 'full_project_qualified': False,
            'assessment_completed': False}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_retained(path, expected_sha, manifest_raw, *, current_primary=False):
    """Read a bounded immutable archive and reconstruct native request bindings."""
    if not isinstance(expected_sha, str) or re.fullmatch(r'[a-f0-9]{64}', expected_sha) is None:
        raise ValueError('diagnostic_archive_identity_invalid')
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError('diagnostic_archive_size_invalid')
    raw = path.read_bytes()
    if current_primary and (expected_sha != CURRENT_ARCHIVE_SHA or len(raw) != 22698583):
        raise ValueError('diagnostic_current_archive_identity')
    if sha(raw) != expected_sha:
        raise ValueError('diagnostic_archive_digest_mismatch')
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if (len(infos) > (128 if current_primary else 100) or sum(i.file_size for i in infos) > MAX_UNPACKED_BYTES
                or len({i.filename for i in infos}) != len(infos)
                or any(PurePosixPath(i.filename).is_absolute() or '..' in PurePosixPath(i.filename).parts
                       or '\\' in i.filename or i.file_size > 48*1024*1024 for i in infos)):
            raise ValueError('diagnostic_archive_members_invalid')
        if current_primary and len(infos) != 108:
            raise ValueError('diagnostic_current_archive_count')
        if current_primary and archive.testzip() is not None:
            raise ValueError('diagnostic_current_archive_integrity')
        receipt_name = 'cpp-baseline-qualification/receipt.json'
        receipt = json.loads(archive.read(receipt_name))
        manifest = json.loads(manifest_raw)
        source = receipt['source']
        if (receipt['benchmark_sha256'] != sha(manifest_raw)
                or any(source[k] != manifest[k] for k in ('repository', 'commit_sha', 'tree_sha'))
                or source['inventory_complete'] is not True):
            raise ValueError('diagnostic_source_identity_mismatch')
        def artifact(key):
            candidates = [i for i in infos if i.filename.startswith('cpp-baseline-qualification/artifacts/' + key + '-')]
            if len(candidates) != 1:
                raise ValueError('diagnostic_artifact_missing_or_ambiguous')
            data = archive.read(candidates[0])
            if not candidates[0].filename.endswith('-' + sha(data) + '.json'):
                raise ValueError('diagnostic_artifact_digest_mismatch')
            return data
        if current_primary:
            verify_current_export(archive, receipt)
        runtime_raw = artifact('project-runtime-evidence')
        snapshot = json.loads(artifact('project-generated-context'))
        compiler_raw = artifact('project-compiler-evidence')
        environment_raw = artifact('project-static-environment')
        primary_raw = artifact('project-static-evidence')
        fallback_raw = None if current_primary else artifact('project-static-clang-fallback')
    probe = receipt['probe']
    database = base64.b64decode(probe['compilation_database'], validate=True)
    if sha(database) != probe['compilation_database_sha256']:
        raise ValueError('diagnostic_database_digest_mismatch')
    from nico.assessment_cpp_project_compiler import project_compiler_request
    from nico.assessment_cpp_static_environment import environment_request, validate_environment
    from nico.assessment_cpp_project_static import project_static_request, validate_project_static
    from nico.assessment_cpp_clang_fallback import clang_fallback_request, validate_clang_fallback
    compiler_request = project_compiler_request(database, source['targets'], snapshot, extended_budget=True)
    environment = validate_environment(environment_raw,
        environment_request(compiler_request, compiler_raw, probe['image_config_digest'],
            collect_completed_compiler_failures=current_primary, snapshot=snapshot,
            physical_header_inputs=current_primary))
    primary_request = project_static_request(database, source['targets'], snapshot, compiler_raw,
        extended_compiler_budget=True, environment=environment, header_provenance=current_primary,
        collect_completed_compiler_failures=current_primary)
    primary = validate_project_static(primary_raw, primary_request)
    if current_primary:
        return {'receipt':receipt, 'manifest':manifest, 'snapshot':snapshot,
            'primary_request':primary_request, 'primary_raw':json.loads(primary_raw),
            'compiler_request':compiler_request, 'compiler_raw':compiler_raw,
            'environment':environment, 'archive_sha256':expected_sha}
    fallback_request = clang_fallback_request(primary_request, primary, extended_budget=True)
    fallback = validate_clang_fallback(fallback_raw, fallback_request, primary_request)
    return {'receipt': receipt, 'manifest': manifest, 'runtime_raw': runtime_raw,
            'snapshot': snapshot, 'fallback_request': fallback_request,
            'fallback_raw': json.loads(fallback_raw), 'fallback_summary': fallback,
            'primary_request': primary_request,
            'archive_sha256': expected_sha}


# An independent before/after cgroup measurement; a full memory peak is not an
# OOM claim. Each measured case owns a fresh container, with no sibling work.
RESOURCE_PROGRAM = r'''
import json, os, pathlib, re
root = pathlib.Path('/sys/fs/cgroup')
def pairs(name):
    try:
        raw = (root/name).read_text(encoding='ascii')
        if len(raw) > 4096: return None
        rows = [r.split() for r in raw.splitlines()]
        if not rows or any(len(r)!=2 or not re.fullmatch(r'[a-z_]+', r[0]) or not r[1].isdigit() for r in rows): return None
        return {k:int(v) for k,v in rows}
    except (OSError,UnicodeError): return None
def number(name):
    try:
        value = (root/name).read_text(encoding='ascii').strip()
        return int(value) if value.isdigit() and len(value)<=20 else None
    except (OSError,UnicodeError): return None
s = os.statvfs('/work')
print(json.dumps({'cpu': pairs('cpu.stat'), 'memory_events': pairs('memory.events'),
 'memory_current_bytes': number('memory.current'), 'memory_peak_bytes': number('memory.peak'),
 'scratch_capacity_bytes': s.f_blocks*s.f_frsize, 'scratch_available_bytes': s.f_bavail*s.f_frsize}, sort_keys=True))
'''


class Sandbox:
    """Diagnostic lifecycle using the production sandbox's exact resource policy."""
    def __init__(self, source, targets, image, output, *, executable, seconds, command=None):
        from nico.assessment_worker_container import _command
        from nico.assessment_worker_capacity_v1 import BASELINE_QUALIFICATION_PROFILE
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', image):
            raise ValueError('diagnostic_image_invalid')
        if type(seconds) is not int or not 1 <= seconds <= 1800:
            raise ValueError('diagnostic_budget_invalid')
        self.source, self.targets, self.image = Path(source), targets, image
        self.output = Path(output); self.output.mkdir(mode=0o700)
        self.executable, self.seconds, self.profile = executable, seconds, BASELINE_QUALIFICATION_PROFILE
        self.name = 'nico-timeout-diagnostic-' + uuid4().hex
        self.command = command or _command
        self.started = time.monotonic(); self.deadline = self.started + seconds
        self.created = False
        self.receipt = {'schema':'nico.native-timeout-diagnostic-sandbox.v1', 'image_config_digest':image,
            'source_population_sha256':sha(canonical_bytes(targets)), 'operations':[],
            'boundary_verified':False, 'scratch_capacity_verified':False,
            'cleanup_required':False, 'cleanup_verified':False, 'production_qualified':False,
            'budget_seconds':seconds, 'executable':executable}

    def save(self):
        self.receipt['duration_ms'] = int((time.monotonic()-self.started)*1000)
        temporary = self.output/'receipt.tmp'
        temporary.write_bytes(canonical_bytes(self.receipt))
        temporary.replace(self.output/'receipt.json')

    def checkpoint(self):
        if time.monotonic() >= self.deadline:
            raise ValueError('diagnostic_deadline')

    def call(self, key, argv, *, data=None, seconds=15, limit=65536, require=True, cleanup=False):
        if not cleanup:
            self.checkpoint()
        start = time.monotonic()
        remaining = seconds if cleanup else min(seconds, self.deadline-start)
        try:
            result = self.command(argv, checkpoint=(lambda: None) if cleanup else self.checkpoint,
                timeout=remaining, input_bytes=data, limit=limit, native_exit=True)
        except BaseException as exc:
            self.receipt['operations'].append({'id':key, 'argv':argv, 'exit_code':None,
                'timed_out':None, 'output_truncated':None, 'error':type(exc).__name__,
                'duration_ms':int((time.monotonic()-start)*1000), 'output_sha256':None,
                'output_bytes':None, 'output_path':None})
            self.save()
            raise
        raw = result['output']
        file = self.output/(str(len(self.receipt['operations']))+'-'+key+'.bin')
        file.write_bytes(raw)
        row = {'id':key, 'argv':argv, 'exit_code':result['exit_code'],
               'timed_out':result['timed_out'], 'output_truncated':result['output_truncated'],
               'duration_ms':int((time.monotonic()-start)*1000), 'output_sha256':sha(raw),
               'output_bytes':len(raw), 'output_path':file.name}
        self.receipt['operations'].append(row); self.save()
        if require and (result['exit_code'] != 0 or result['timed_out'] or result['output_truncated']):
            raise ValueError('diagnostic_operation_failed:'+key)
        return result

    def exec(self, key, argv, *, user=None, env=None, **kwargs):
        prefix = ['docker','exec']
        if user: prefix += ['--user='+user]
        for k,v in sorted((env or {}).items()): prefix += ['--env='+k+'='+v]
        if kwargs.get('data') is not None: prefix += ['--interactive']
        return self.call(key, [*prefix, self.name, *argv], **kwargs)

    def resources(self, key):
        result = self.exec(key, ['python3','-I','-S','-c',RESOURCE_PROGRAM], limit=8192)
        return json.loads(result['output'])

    def read(self, key, path, maximum, *, user=None):
        from nico.assessment_cpp_full_project_execution import READ_PROGRAM
        result = self.exec(key, ['python3','-I','-S','-c',READ_PROGRAM,path,str(maximum)], user=user, limit=2*maximum+4096)
        value = json.loads(result['output'])
        if set(value) != {'data','truncated'} or value['truncated'] is not False:
            raise ValueError('diagnostic_read_truncated')
        return base64.b64decode(value['data'], validate=True)

    def __enter__(self):
        from nico.assessment_cpp_full_project_execution import (
            _inputs, ANALYSIS_USER, ANALYSIS_SETUP_PROGRAM, BOUNDARY_PROGRAM, INPUT_PROGRAM, boundary_valid)
        from nico.assessment_worker_capacity_v1 import docker_resource_args
        from nico.assessment_cpp_full_project import MAX_SOURCE_BYTES
        self.save()
        try:
            image = json.loads(self.call('image',['docker','image','inspect',self.image])['output'])
            if len(image)!=1 or image[0]['Id'] != self.image:
                raise ValueError('diagnostic_image_mismatch')
            self.created = True
            self.receipt['cleanup_required'] = True
            self.call('create', ['docker','create','--name',self.name,'--network=none','--read-only',
                '--user=1000:1000','--cap-drop=ALL','--security-opt=no-new-privileges',
                *docker_resource_args(self.profile, executable=self.executable), '--log-driver=none',
                '--env=HOME=/work','--env=TMPDIR=/work','--entrypoint=sleep',self.image,str(self.seconds+15)])
            self.call('start',['docker','start',self.name])
            setup = json.loads(self.exec('analysis-setup',['python3','-I','-S','-c',ANALYSIS_SETUP_PROGRAM], user=ANALYSIS_USER)['output'])
            if setup != {'uid':1001,'gid':1001,'private':True}: raise ValueError('diagnostic_analysis_boundary')
            before = json.loads(self.exec('boundary-before',['python3','-I','-S','-c',BOUNDARY_PROGRAM])['output'])
            if not boundary_valid(before, source_required=False, profile=self.profile, executable=self.executable):
                raise ValueError('diagnostic_boundary_invalid')
            files = _inputs({'targets':self.targets,'configuration':{'source_byte_limit':MAX_SOURCE_BYTES}}, self.source, self.checkpoint)
            data = canonical_bytes(files)
            transferred = json.loads(self.exec('source',['python3','-I','-S','-c',INPUT_PROGRAM,str(len(data))],
                user='0:0',data=data,seconds=30,limit=4*1024*1024)['output'])
            if transferred != self.targets: raise ValueError('diagnostic_source_mismatch')
            after = json.loads(self.exec('boundary-after',['python3','-I','-S','-c',BOUNDARY_PROGRAM])['output'])
            self.receipt['boundary_verified'] = boundary_valid(after, profile=self.profile, executable=self.executable)
            self.receipt['boundary'] = after; self.save()
            if not self.receipt['boundary_verified']: raise ValueError('diagnostic_boundary_invalid')
            from nico.assessment_worker_capacity_v1 import resources_for
            observed = self.resources('scratch-capacity')
            self.receipt['scratch_capacity_bytes'] = observed.get('scratch_capacity_bytes')
            self.receipt['scratch_capacity_verified'] = (
                type(observed.get('scratch_capacity_bytes')) is int and
                observed['scratch_capacity_bytes'] == resources_for(self.profile)['tmpfs_bytes'])
            self.save()
            if not self.receipt['scratch_capacity_verified']:
                raise ValueError('diagnostic_scratch_capacity_mismatch')
            return self
        except BaseException as exc:
            self.__exit__(type(exc),exc,exc.__traceback__)
            raise

    def __exit__(self, kind, value, tb):
        try:
            if self.created:
                result = self.call('cleanup',['docker','rm','--force',self.name],seconds=5,
                    limit=4096,require=False,cleanup=True)
                self.receipt['cleanup_verified'] = bool(result['exit_code']==0 and
                    not result['timed_out'] and not result['output_truncated'])
            else:
                self.receipt['cleanup_verified'] = True
        except Exception as exc:
            self.receipt['cleanup_error'] = type(exc).__name__
            self.receipt['cleanup_verified'] = False
        if not self.receipt['cleanup_verified']:
            self.receipt.setdefault('cleanup_error','diagnostic_cleanup_unproven')
        self.save()
        if not self.receipt['cleanup_verified'] and kind is None:
            raise ValueError('diagnostic_cleanup_unproven')
        return False


def select_cases(retained, scope_raw, test_name, context_id):
    from nico.assessment_cpp_runtime_scope import validate_retained_runtime
    from nico.assessment_cpp_runtime_execution import _output
    from xml.etree import ElementTree
    receipt, manifest = retained['receipt'], retained['manifest']
    if sha(scope_raw) != receipt['runtime_scope_sha256']:
        raise ValueError('diagnostic_runtime_scope_mismatch')
    runtime = validate_retained_runtime(retained['runtime_raw'], receipt['source']['targets'],
        manifest['project_options'], json.loads(scope_raw))
    value = json.loads(retained['runtime_raw'])
    rows = [r for r in value['evidence']['sanitizers'] if r['kind']=='address']
    if len(rows)!=1 or not isinstance(rows[0].get('results'), dict):
        raise ValueError('diagnostic_retained_test_missing')
    tests = rows[0]['results']
    if (test_name not in tests['executed'] or test_name in tests['passed']
            or test_name in tests['skipped']):
        raise ValueError('diagnostic_retained_test_not_failed')
    junit_wrapper = json.loads(_output(rows[0]['junit_read'], 8*1024*1024))
    if junit_wrapper.get('truncated') is not False:
        raise ValueError('diagnostic_retained_junit_truncated')
    junit = base64.b64decode(junit_wrapper['data'], validate=True)
    if sha(junit) != rows[0]['junit_sha256']:
        raise ValueError('diagnostic_retained_junit_digest')
    cases = [c for c in ElementTree.fromstring(junit).iter('testcase') if c.get('name')==test_name]
    if len(cases)!=1 or not any('timeout' in (str(c.attrib)+str(c.text)).lower()
                               for c in cases[0] if c.tag in {'failure','error'}):
        raise ValueError('diagnostic_retained_test_not_timeout')
    contexts = [r for r in retained['fallback_request']['contexts'] if r['context_id']==context_id]
    records = [r for r in retained['fallback_raw']['records'] if r['context_id']==context_id]
    if (len(contexts)!=1 or len(records)!=1 or not isinstance(records[0].get('execution'),dict)
            or records[0]['execution']['timed_out'] is not True):
        raise ValueError('diagnostic_retained_context_not_timeout')
    isolated_ctest_argv(tests['required'], test_name, runtime['plan']['sanitizers']['test_case_seconds'])
    return {'test_name':test_name,'context':contexts[0], 'runtime_plan':runtime['plan'],
            'old_test_result':tests, 'old_test_operation':rows[0]['tests'],
            'old_context_execution':records[0]['execution'],
            'fallback_request':isolated_fallback_request(retained['fallback_request'],context_id),
            'primary_request':retained['primary_request']}


BINARY_IDENTITY_PROGRAM = r'''
import hashlib, json, os, pathlib, stat, sys
p = pathlib.Path(sys.argv[1]); root = pathlib.Path('/work/sanitize-address')
if (not p.is_absolute() or root not in p.parents or p != p.resolve(strict=True)):
    raise SystemExit(2)
fd = os.open(p, os.O_RDONLY|os.O_NOFOLLOW)
try:
    before=os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=1024**3: raise SystemExit(2)
    h=hashlib.sha256()
    with os.fdopen(fd,'rb',closefd=False) as f:
        while True:
            b=f.read(1024*1024)
            if not b: break
            h.update(b)
    after=os.fstat(fd)
    if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns): raise SystemExit(2)
    print(json.dumps({'path':str(p),'bytes':before.st_size,'sha256':h.hexdigest()}))
finally: os.close(fd)
'''


def run_address(source, targets, image, output, selected, options, asset_directory):
    from nico.assessment_cpp_configuration_probe import UNIT_TEST_DATA_PROGRAM
    from nico.assessment_cpp_runtime_execution import LOG_EXEC_PROGRAM, _base_options, _discover, _junit
    plan = selected['runtime_plan']; asset = plan.get('unit_test_data')
    result = {'scope':'one_isolated_address_sanitizer_test','complete':False,'production_qualified':False}
    box = Sandbox(source, targets, image, output, executable=True, seconds=1800)
    try:
        with box:
            if asset is not None:
                directory = Path(asset_directory)
                if directory.is_symlink() or not directory.is_dir() or sorted(p.name for p in directory.iterdir()) != [asset['name']]:
                    raise ValueError('diagnostic_asset_population_mismatch')
                path = directory/asset['name']
                if path.is_symlink() or path.stat().st_size != asset['bytes']:
                    raise ValueError('diagnostic_asset_size_mismatch')
                raw = path.read_bytes()
                if sha(raw)!=asset['sha256']: raise ValueError('diagnostic_asset_digest_mismatch')
                payload = canonical_bytes({asset['name']:{'base64':base64.b64encode(raw).decode(), 'sha256':sha(raw)}})
                returned = json.loads(box.exec('unit-data',['python3','-I','-S','-c',UNIT_TEST_DATA_PROGRAM,str(len(payload))],
                    user='0:0',data=payload,seconds=20)['output'])
                if returned != {asset['name']:asset['sha256']}: raise ValueError('diagnostic_asset_transfer_mismatch')
            if box.exec('compiler-version',['g++','-dumpfullversion'])['output'].strip()!=b'14.2.0':
                raise ValueError('diagnostic_compiler_version_mismatch')
            if box.exec('cmake-version',['cmake','--version'])['output'].splitlines()[0]!=b'cmake version 3.31.6':
                raise ValueError('diagnostic_cmake_version_mismatch')
            directory = '/work/sanitize-address'
            box.exec('configure',['cmake','-S','/work/source','-B',directory,'-G','Unix Makefiles',
                '-DCMAKE_BUILD_TYPE=Debug','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
                '-DCMAKE_C_COMPILER=/usr/local/bin/gcc','-DCMAKE_CXX_COMPILER=/usr/local/bin/g++',
                *_base_options(options),'-DSANITIZERS=address'], seconds=90, limit=1024*1024)
            box.exec('build',['cmake','--build',directory,'--parallel',str(plan['sanitizers']['parallel'])],
                seconds=plan['sanitizers']['build_seconds'], limit=1024*1024)
            discovery = box.exec('discovery',['ctest','--test-dir',directory,'--show-only=json-v1'],seconds=60,limit=4*1024*1024)['output']
            names = _discover(discovery)
            if names != selected['old_test_result']['required']:
                raise ValueError('diagnostic_discovery_membership_mismatch')
            details = [r for r in json.loads(discovery)['tests'] if r['name']==selected['test_name']]
            if len(details)!=1 or not isinstance(details[0].get('command'), list) or not details[0]['command']:
                raise ValueError('diagnostic_test_executable_missing')
            binary = details[0]['command'][0]
            before_binary = json.loads(box.exec('binary-before',['python3','-I','-S','-c',BINARY_IDENTITY_PROGRAM,binary],seconds=20)['output'])
            symbols = box.exec('asan-symbols',['nm','-u',binary],seconds=20,limit=1024*1024)['output']
            if b'__asan_init' not in symbols: raise ValueError('diagnostic_asan_instrumentation_unproven')
            argv = isolated_ctest_argv(names, selected['test_name'], plan['sanitizers']['test_case_seconds'])
            before = box.resources('resources-before')
            env = {'ASAN_OPTIONS':'detect_leaks=0:halt_on_error=1'}
            if asset is not None: env['DIR_UNIT_TEST_DATA']='/work/unit_test_data'
            native = box.exec('isolated-test',['python3','-I','-S','-c',LOG_EXEC_PROGRAM,
                directory+'/nico-runtime-ctest.log',*argv],seconds=plan['sanitizers']['test_seconds'],
                env=env,require=False,limit=1024*1024)
            after = box.resources('resources-after')
            result.update(resources_before=before,resources_after=after,resource_delta=metrics_delta(before,after),
                test_name=selected['test_name'],discovery_count=len(names),discovery_sha256=sha(discovery),
                binary=before_binary,asan_symbol_observed=True,actual_test_argv=argv,
                test_exit_code=native['exit_code'],test_timed_out=native['timed_out'])
            box.receipt['result']=result; box.save()
            log = box.read('test-log',directory+'/nico-runtime-ctest.log',1024*1024)
            (box.output/'ctest.log').write_bytes(log)
            junit = box.read('test-junit',directory+'/nico-diagnostic-junit.xml',4*1024*1024)
            (box.output/'junit.xml').write_bytes(junit)
            summary = _junit(junit,[selected['test_name']])
            after_binary = json.loads(box.exec('binary-after',['python3','-I','-S','-c',BINARY_IDENTITY_PROGRAM,binary],seconds=20)['output'])
            if before_binary!=after_binary: raise ValueError('diagnostic_test_executable_changed')
            result.update(junit=summary,junit_sha256=sha(junit),log_sha256=sha(log),
                binary_unchanged=True,complete=bool(native['exit_code']==0 and not native['timed_out']
                    and not native['output_truncated'] and summary['passed']==[selected['test_name']]
                    and summary['executed']==[selected['test_name']] and not summary['skipped']))
    except Exception as exc:
        result['error']=str(exc) if str(exc).startswith('diagnostic_') else type(exc).__name__
    finally:
        result.update(boundary_verified=box.receipt['boundary_verified'],cleanup_verified=box.receipt['cleanup_verified'])
        box.receipt['result']=result; box.save()
    return result


def run_static(source, targets, image, output, selected, snapshot):
    from nico.assessment_cpp_project_snapshot import PROJECT_RESTORE_PROGRAM
    from nico.assessment_cpp_full_project_execution import ANALYSIS_USER
    from nico.assessment_cpp_clang_fallback import PROGRAM, STREAM_LIMIT, validate_clang_fallback, _decode_plist
    result = {'scope':'one_isolated_clang_context','complete':False,'production_qualified':False,
              'full_project_qualified':False, 'original_case_limit_seconds':120}
    box = Sandbox(source, targets, image, output, executable=False, seconds=240)
    context = selected['context']; request = selected['fallback_request']
    try:
        with box:
            restore = {'schema':'nico.cpp-project-restore.v1','files':snapshot['files'],
                       'file_population_sha256':snapshot['file_population_sha256']}
            restored = json.loads(box.exec('generated-restore',['python3','-I','-S','-c',PROJECT_RESTORE_PROGRAM],
                user=ANALYSIS_USER,data=canonical_bytes(restore),seconds=30,limit=4*1024*1024)['output'])
            expected = {'file_population_sha256':snapshot['file_population_sha256'],
                'files':{p:{'sha256':v['sha256'],'bytes':v['bytes']} for p,v in sorted(snapshot['files'].items())}}
            if restored!=expected: raise ValueError('diagnostic_generated_restore_mismatch')
            before = box.resources('resources-before')
            # Reuse the unchanged collector: private UID, exact cwd/environment,
            # 4 MiB file limit, dependency checks and process-group cleanup.
            # Only one context is supplied. Its case limit remains 120 seconds.
            native = box.exec('isolated-context',['python3','-I','-S','-c',PROGRAM],
                user=ANALYSIS_USER,data=canonical_bytes(request),seconds=150,
                require=False,limit=STREAM_LIMIT)
            after = box.resources('resources-after')
            result.update(context_id=context['context_id'],analysis_file=context['analysis_file'],
                source_dependencies=context['source_dependencies'],generated_dependencies=context['generated_dependencies'],
                invocation=context['invocation'],resources_before=before,resources_after=after,
                resource_delta=metrics_delta(before,after),collector_exit_code=native['exit_code'],
                collector_timed_out=native['timed_out'],request_sha256=sha(canonical_bytes(request)),
                retained_required_contexts_count=len(request['required_contexts']),selected_contexts_count=1)
            box.receipt['result']=result; box.save()
            if native['exit_code']!=0 or native['timed_out'] or native['output_truncated']:
                raise ValueError('diagnostic_collector_failed')
            proof = validate_clang_fallback(native['output'],request,selected['primary_request'])
            rows = json.loads(native['output'])['records']
            if len(rows)!=1: raise ValueError('diagnostic_context_population_mismatch')
            execution=rows[0]['execution']
            result.update(exit_code=None if execution is None else execution['exit_code'],
                timed_out=None if execution is None else execution['timed_out'],
                native_duration_ms=None if execution is None else execution['duration_ms'],
                native_error=rows[0]['error'],native_evidence_sha256=sha(native['output']),
                automated_observation_count=len(proof['findings']),
                complete=proof['complete'] is True and proof['analyzed_contexts']==[context['context_id']])
            if rows[0]['plist']:
                raw=_decode_plist(rows[0]['plist'],rows[0]['plist_sha256'])
                (box.output/'analysis.plist').write_bytes(raw)
                result['plist_sha256']=sha(raw)
    except Exception as exc:
        result['error']=str(exc) if str(exc).startswith('diagnostic_') else type(exc).__name__
    finally:
        result.update(boundary_verified=box.receipt['boundary_verified'],cleanup_verified=box.receipt['cleanup_verified'])
        box.receipt['result']=result; box.save()
    return result


def owned_control(image, output):
    """Exercise the actual disposable wrapper before a retained-source diagnostic.

    This is a tiny owned transport/isolation control, not full-project or Bitcoin
    qualification. The deliberately failing program must retain exit seven.
    """
    import tempfile
    output=Path(output); output.mkdir(mode=0o700)
    evidence={'schema':'nico.native-timeout-owned-control.v1','passed':False,
              'production_qualified':False,'assessment_completed':False,'cases':[]}
    try:
        with tempfile.TemporaryDirectory(prefix='nico-owned-timeout-') as temporary:
            root=Path(temporary)
            data=b'int main(int argc, char**) { return argc > 1 ? 7 : 0; }\n'
            (root/'main.cpp').write_bytes(data)
            targets={'main.cpp':sha(data)}
            box=Sandbox(root,targets,image,output/'executable',executable=True,seconds=60)
            with box:
                box.exec('owned-compile',['g++','-g','-O0','-fsanitize=address',
                    '/work/source/main.cpp','-o','/work/owned'],seconds=20)
                env={'ASAN_OPTIONS':'detect_leaks=0:halt_on_error=1'}
                box.exec('owned-success',['/work/owned'],env=env)
                failure=box.exec('owned-expected-failure',['/work/owned','fail'],env=env,require=False)
                if failure['exit_code']!=7 or failure['timed_out'] or failure['output_truncated']:
                    raise ValueError('diagnostic_owned_failure_not_retained')
            if not box.receipt['cleanup_verified']: raise ValueError('diagnostic_owned_cleanup_unproven')
            evidence['cases'].append({'case':'owned_address_success_and_exit_seven','passed':True})
            box=Sandbox(root,targets,image,output/'noexec',executable=False,seconds=60)
            with box:
                box.exec('owned-syntax',['/usr/lib/llvm-17/bin/clang++','-fsyntax-only',
                    '/work/source/main.cpp'],user='1001:1001',seconds=20)
            if not box.receipt['cleanup_verified']: raise ValueError('diagnostic_owned_cleanup_unproven')
            evidence['cases'].append({'case':'owned_noexec_syntax_and_cleanup','passed':True})
            evidence['passed']=True
    finally:
        (output/'control.json').write_bytes(canonical_bytes(evidence))
    return evidence


CURRENT_ARCHIVE_SHA = 'dbf890120e44a7d0f99133d69f316c9e8d7dce0210f3ae627e248ffa1c4e7e92'
CURRENT_IMAGE = 'sha256:a69e33207d15970ff60cc7c6e7a26b78f2cdf5534757fbb70bada0d61d3b5e97'
CURRENT_PRODUCER = '457c173391d02c44f90b32be17e3697a2da1a690'
CURRENT_TOOLS = {'cppcheck':'f5215eabbc2666859254ace73a5f53eb991cb285f94a733d6682ea85f26d2544',
    'nico-clang-header-observer.so':'45474684723784ea89d5531bf52730adedddc312814c083e990e8a2df1bf43f9'}
CURRENT_CASES = {2:'src/init/basic.cpp', 4:'src/init/bitcoin-node.cpp', 10:'src/compat/stdin.cpp'}
DIAGNOSTIC_FLAGS = ['--showtime=file', '--report-progress=1']


def verify_current_export(archive, receipt):
    """Hash every exported file without extracting or executing archive members."""
    manifest = json.loads(archive.read('cpp-collection-toolchain-manifest.json'))
    files = manifest.get('files')
    if (receipt.get('producer_source_sha') != CURRENT_PRODUCER
            or receipt['probe']['image_config_digest'] != CURRENT_IMAGE
            or manifest.get('image_config_digest') != CURRENT_IMAGE
            or manifest.get('schema') != 'nico.cpp-collection-tool-export.v1'
            or not isinstance(files, dict) or len(files) != 74):
        raise ValueError('diagnostic_current_export_binding')
    for name, row in files.items():
        parts = PurePosixPath(name)
        if (parts.is_absolute() or '..' in parts.parts or '\\' in name
                or parts.as_posix() != name or not name):
            raise ValueError('diagnostic_current_export_path')
        limit = 32*1024*1024 if name == 'cppcheck' else 4*1024*1024 if name.endswith('.so') else 1024*1024
        info = archive.getinfo('cpp-collection-toolchain/' + name)
        if info.file_size > limit or info.is_dir():
            raise ValueError('diagnostic_current_export_size')
        raw = archive.read(info)
        if row != {'size_bytes':len(raw), 'sha256':sha(raw)}:
            raise ValueError('diagnostic_current_export_digest')
    if any(files.get(name, {}).get('sha256') != digest for name,digest in CURRENT_TOOLS.items()):
        raise ValueError('diagnostic_current_tool_identity')
    image = archive.read('cpp-collection-toolchain/image-config-digest.txt').decode().strip()
    metadata = json.loads(archive.read('cpp-collection-toolchain/image.json'))
    if image != CURRENT_IMAGE or len(metadata) != 1 or metadata[0].get('Id') != image:
        raise ValueError('diagnostic_current_image_identity')


def select_primary_cases(retained):
    request = retained['primary_request']; records = retained['primary_raw']['records']
    if (request.get('schema') != 'nico.cpp-project-static-request.v4'
            or len(request['contexts']) != 577 or len(records) != 577
            or request['limits'] != {'wall_seconds':540,'case_seconds':90,'parallel':2}):
        raise ValueError('diagnostic_current_population')
    selected = []
    for index, path in CURRENT_CASES.items():
        context, record = request['contexts'][index], records[index]
        execution = record.get('execution')
        if (context['index'] != index or context['path'] != path
                or context['context_id'] != record['context_id']
                or record['invocation'] != context['analyzer_invocation']
                or not isinstance(execution, dict)
                or execution['timed_out'] is not (index != 10)
                or index == 10 and (execution['exit_code'] != 0 or execution['output_truncated'])):
            raise ValueError('diagnostic_current_case_binding')
        selected.append({'index':index,'path':path,'context_id':context['context_id'],
            'database_sha256':context['analyzer_database_sha256'],
            'invocation':context['analyzer_invocation'] + DIAGNOSTIC_FLAGS,
            'retained_execution':execution})
    return selected


def primary_program():
    """Reuse production validation/collection with a diagnostic-only scheduler.

    Full request indexing and input validation are preserved. The scheduler
    dispatches ONLY the three reviewed contexts, serially; no production receipt
    validator is applied to this intentionally partial, instrumented result.
    """
    from nico.assessment_cpp_project_static import PROGRAM
    suffix = '\nrun_project_static()\n'
    if not PROGRAM.endswith(suffix):
        raise ValueError('diagnostic_collector_entrypoint_changed')
    return PROGRAM[:-len(suffix)] + '\n' + textwrap.dedent(r'''
        import sys
        original_run = _run
        def _run(argv, stem, deadline, environment):
            actual = list(argv)
            if actual[0] == '/usr/local/bin/cppcheck' and '--version' not in actual:
                actual += ['--showtime=file', '--report-progress=1']
            result = original_run(actual, stem, min(deadline, time.monotonic()+90), environment)
            return result
        class ThreadPoolExecutor:
            def __init__(self, max_workers):
                if max_workers != 2: raise ValueError('diagnostic_parallel_contract')
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def map(self, function, contexts):
                expected = {2:'src/init/basic.cpp',4:'src/init/bitcoin-node.cpp',10:'src/compat/stdin.cpp'}
                if len(contexts) != 577: raise ValueError('diagnostic_population')
                for index,path in expected.items():
                    if contexts[index]['index'] != index or contexts[index]['path'] != path:
                        raise ValueError('diagnostic_selection')
                for index in expected:
                    row = function(contexts[index])
                    row['executed_invocation'] = (row['invocation'] + ['--showtime=file','--report-progress=1']
                                                  if row.get('execution') is not None else None)
                    print(_canonical({'diagnostic_partial_record':row}).decode(), flush=True)
                    yield row
        raw = sys.stdin.buffer.read(REQUEST_LIMIT+1)
        if len(raw)>REQUEST_LIMIT: raise ValueError('diagnostic_request_limit')
        request=json.loads(raw)
        if request['limits'] != {'wall_seconds':540,'case_seconds':90,'parallel':2}:
            raise ValueError('diagnostic_limits')
        result=collect_project_static(request)
        result.update(schema='nico.current-primary-diagnostic.v1', production_qualified=False,
            assessment_completed=False, full_project_qualified=False,
            diagnostic_flags=['--showtime=file','--report-progress=1'],
            dispatched_indices=[2,4,10], diagnostic_parallel=1, retained_population=577)
        print(_canonical(result).decode(), flush=True)
    ''')


def run_primary(source, targets, image, output, retained):
    from nico.assessment_cpp_project_snapshot import PROJECT_RESTORE_PROGRAM
    from nico.assessment_cpp_static_environment import environment_request, validate_environment, ENV_PROGRAM, ENV_STREAM_LIMIT
    from nico.assessment_cpp_project_static import STREAM_LIMIT
    selected = select_primary_cases(retained)
    snapshot = retained['snapshot']
    result = {'scope':'three_current_primary_contexts','complete':False,
        'selected':selected,'retained_population':577,'unselected_contexts':574,
        'production_qualified':False,'assessment_completed':False,'full_project_qualified':False,
        'case_seconds':90,'total_seconds':540,'diagnostic_parallel':1,
        'retained_image':CURRENT_IMAGE,'diagnostic_image':image,
        'original_image_replay':False,
        'timing_limits':'Completed CPU phases can overlap and add overhead; killed phases do not identify a precise hotspot.'}
    box = Sandbox(source,targets,image,output,executable=False,seconds=540)
    try:
        with box:
            identity = "import hashlib,json,pathlib; paths=['/usr/local/bin/cppcheck','/opt/nico-clang-header-observer.so']; assert all(pathlib.Path(p).is_file() and pathlib.Path(p).stat().st_size <= 32*1024*1024 for p in paths); print(json.dumps({p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in paths}))"
            observed=json.loads(box.exec('tool-identity',['python3','-I','-S','-c',identity],user='1001:1001')['output'])
            if observed != {'/usr/local/bin/cppcheck':CURRENT_TOOLS['cppcheck'],
                            '/opt/nico-clang-header-observer.so':CURRENT_TOOLS['nico-clang-header-observer.so']}:
                raise ValueError('diagnostic_rebuilt_tool_identity')
            restore={'schema':'nico.cpp-project-restore.v1','files':snapshot['files'],
                     'file_population_sha256':snapshot['file_population_sha256']}
            restored=json.loads(box.exec('generated-restore',['python3','-I','-S','-c',PROJECT_RESTORE_PROGRAM],
                user='1001:1001',data=canonical_bytes(restore),seconds=30,limit=4*1024*1024)['output'])
            expected={'file_population_sha256':snapshot['file_population_sha256'],
                      'files':retained['compiler_request']['generated_files']}
            if restored != expected: raise ValueError('diagnostic_generated_restore_mismatch')
            env_request=environment_request(retained['compiler_request'],retained['compiler_raw'],image,
                collect_completed_compiler_failures=True,snapshot=snapshot,physical_header_inputs=True)
            env_raw=box.exec('environment',['python3','-I','-S','-c',ENV_PROGRAM],user='1001:1001',
                data=canonical_bytes(env_request),seconds=40,limit=ENV_STREAM_LIMIT)['output']
            model=validate_environment(env_raw,env_request)
            ignored={'request_sha256','native_evidence_sha256','image_config_digest'}
            if {k:v for k,v in model.items() if k not in ignored} != {k:v for k,v in retained['environment'].items() if k not in ignored}:
                raise ValueError('diagnostic_environment_bytes_changed')
            before=box.resources('resources-before')
            native=box.exec('current-primary',['python3','-I','-S','-c',primary_program()],user='1001:1001',
                data=canonical_bytes(retained['primary_request']),seconds=540,limit=STREAM_LIMIT,require=False)
            after=box.resources('resources-after')
            result.update(resources_delta=metrics_delta(before,after),exit_code=native['exit_code'],
                          timed_out=native['timed_out'],output_truncated=native['output_truncated'])
            if native['exit_code']==0 and not native['timed_out'] and not native['output_truncated']:
                evidence=json.loads(native['output'].splitlines()[-1])
                if evidence.get('schema')!='nico.current-primary-diagnostic.v1' or [r['context_id'] for r in evidence['records']] != [r['context_id'] for r in selected]:
                    raise ValueError('diagnostic_result_binding')
                result['evidence']=evidence
                result['complete']=all(r['execution'] and r['execution']['exit_code']==0 and not r['execution']['timed_out'] and not r['execution']['output_truncated'] and r['error'] is None for r in evidence['records'])
    finally:
        result.update(boundary_verified=box.receipt['boundary_verified'],cleanup_verified=box.receipt['cleanup_verified'])
        box.receipt['result']=result;box.save()
    return result


def owned_primary_control(image, output):
    """Owned static-only isolation control; never compile or run a project binary."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix='nico-owned-primary-') as temporary:
        source=Path(temporary); raw=b'int main() { return 0; }\n'
        (source/'owned.cpp').write_bytes(raw)
        box=Sandbox(source,{'owned.cpp':sha(raw)},image,output,executable=False,seconds=60)
        with box:
            box.exec('owned-primary',['/usr/local/bin/cppcheck','--xml','--enable=warning,style,performance,portability,information,missingInclude',
                '--check-level=exhaustive','--max-configs=1','--platform=unix64','-j1',
                '--showtime=file','--report-progress=1','/work/source/owned.cpp'],user='1001:1001',seconds=30)
        if not box.receipt['cleanup_verified']:
            raise ValueError('diagnostic_owned_cleanup_unproven')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--archive-sha256',required=True)
    parser.add_argument('--qualification-source',type=Path,required=True)
    parser.add_argument('--qualification-manifest',type=Path,required=True)
    parser.add_argument('--mode',choices=['current-primary'],required=True)
    parser.add_argument('--image',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.archive_sha256 != CURRENT_ARCHIVE_SHA:
        raise ValueError('diagnostic_current_archive_required')
    args.output.mkdir(mode=0o700)
    outcome={'schema':'nico.current-primary-diagnostic-controller.v1',
             **diagnostic_status(False,False,False,False)}
    import tempfile
    from scripts.qualify_cpp_project_configuration import freeze_configuration_checkout
    try:
        retained=load_retained(args.archive,args.archive_sha256,args.qualification_manifest.read_bytes(),current_primary=True)
        select_primary_cases(retained)
        with tempfile.TemporaryDirectory(prefix='nico-current-primary-') as temporary:
            root=Path(temporary)/'source'
            source=freeze_configuration_checkout(args.qualification_source,root,retained['manifest'])
            if source['targets'] != retained['receipt']['source']['targets']:
                raise ValueError('diagnostic_frozen_population_mismatch')
            outcome['static']=run_primary(root,source['targets'],args.image,args.output/'static',retained)
            result=outcome['static']
            outcome.update(diagnostic_status(True,result['complete'],result['boundary_verified'],result['cleanup_verified']))
    except Exception as exc:
        outcome['error']=str(exc) if str(exc).startswith('diagnostic_') else type(exc).__name__
        raise
    finally:
        (args.output/'diagnostic.json').write_bytes(canonical_bytes(outcome))
    if outcome['status']!='ISOLATED_CASES_COMPLETED': raise SystemExit(1)


if __name__=='__main__':
    main()
