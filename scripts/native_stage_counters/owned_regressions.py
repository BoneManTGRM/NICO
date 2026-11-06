"""Explicit owned-only build/test harness; importing this module executes nothing.

Use a private, trusted pinned checkout with production repairs, grouping and
counters already applied. No assessed source, network, installs or workflows.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import time
from .binding import AFTER_SHA256, HEADER_SHA256
from .instrument import read_regular

ROOT = Path(__file__).parent
PRODUCTION_SOURCE_SHA256 = {'lib/tokenize.cpp': '76beaa920046dbe057c5b20b09c043802351692657e2b3f269cf4612984eac88', 'lib/token.cpp': 'f4e7b9234f1af3cd37dfd1b0dee6d17732c36abd830ae1c5200b118220795e1a', 'lib/tokenlist.cpp': '46c45075c864aa1e6783bc64ced1a95d03c3fddf37180c944cfb3087d47c919f', 'externals/simplecpp/simplecpp.cpp': '7f92c920b66ad9a0ba82fa460f25be2721e28ded51e0d66992976e3c11a9e8a5', 'externals/simplecpp/simplecpp.h': '900f3608d157b4553566abc4f43cc6249005e9cc489707661984a52b32292633', 'lib/cppcheck.cpp': '377cde381b0f6b3b4ea55ec8beeea4691992628f18589e8238f344e49ba078bd', 'lib/cppcheck.h': 'c298b694faf230b2b66233d02b1a1a3351c03e10ceeb46a5ba1f53f616b801c0', 'lib/preprocessor.cpp': 'acf71bb200123151ae978f7d9611d010ade2e2ec5b21508505638d522e214852', 'lib/preprocessor.h': 'c255dbb80348c3699dbf3d5c46e771b28adeb50b93ce20778388b173a269633c', 'lib/templatesimplifier.h': '92e8f21cca8a74e36fee87ce00f903ae76c35900bb04d6034ba2d90dc7dff0f6', 'Makefile': 'b89eb19daa5e910a56e29e38840bdbee6a7a38000dfb39d282563039846298fa'}
PATCH_SHA256 = '1325897d39c0de3d25b17579337948b66ee95c0d8ae96f1d6794e1626e0d093e'
BEFORE_SHA256 = '0a5714635894140207f286540e6a5f3870eca527309c54c9e18348a0859ce15a'
AFTER_TEST_SHA256 = '390f5b7c25a8d27325297aa8d8bb69d4089e0a76c9a0d83034c7f60dd9596c3f'
COMPILER = Path('/usr/bin/g++-14')
COMPILER_SHA256 = '6b3696e4dcb85e1c949c732a02befa50e3983ecf94ce7e8e58d9d503b954b79d'
MAKE = Path('/usr/bin/make')
MAKE_SHA256 = '8a229baf64671988cfb5af43ba3070c6ce7214cf32bcf96155115559d1466fa7'
NAMES_SHA256 = 'c7cf1bf48b5fe5f0edf8bcb8ec53bcaadcc5b5bee10129f336c9c2468647d40f'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def apply_fixture(raw, patch):
    if digest(raw) != BEFORE_SHA256 or digest(patch) != PATCH_SHA256:
        raise ValueError('owned_fixture_input_identity')
    lines = raw.splitlines(keepends=True); diff = patch.splitlines(keepends=True)
    result = []; cursor = 0; index = 2
    if diff[:2] != [b'--- a/test/testsimplifytemplate.cpp\n', b'+++ b/test/testsimplifytemplate.cpp\n']:
        raise ValueError('owned_fixture_patch_header')
    while index < len(diff):
        match = re.fullmatch(rb'@@ -(\d+),(\d+) \+(\d+),(\d+) @@\n', diff[index])
        if not match:
            raise ValueError('owned_fixture_hunk')
        start, old_count, new_start, new_count = map(int, match.groups())
        if start-1 < cursor:
            raise ValueError('owned_fixture_hunk_order')
        result.extend(lines[cursor:start-1]); cursor = start-1
        if len(result) != new_start-1:
            raise ValueError('owned_fixture_hunk_position')
        index += 1; old_seen = new_seen = 0
        while index < len(diff) and not diff[index].startswith(b'@@ '):
            row = diff[index]; index += 1
            if row[:1] in (b' ', b'-'):
                if cursor >= len(lines) or lines[cursor] != row[1:]:
                    raise ValueError('owned_fixture_context')
                cursor += 1; old_seen += 1
            if row[:1] in (b' ', b'+'):
                result.append(row[1:]); new_seen += 1
            if row[:1] not in (b' ', b'+', b'-'):
                raise ValueError('owned_fixture_line')
        if (old_seen, new_seen) != (old_count, new_count):
            raise ValueError('owned_fixture_hunk_counts')
    result.extend(lines[cursor:]); updated = b''.join(result)
    if digest(updated) != AFTER_TEST_SHA256:
        raise ValueError('owned_fixture_output_identity')
    return updated


def expected_names():
    raw = read_regular(ROOT/'owned-case-names.json')
    if digest(raw) != NAMES_SHA256:
        raise ValueError('owned_fixture_names_identity')
    return json.loads(raw)


def verdict(stdout, stderr, execution):
    expected = expected_names()
    actual = [line for line in stdout.splitlines() if line.startswith('TestSimplifyTemplate::')]
    counts = re.findall(r'^Number of tests: (\d+)$', stdout, re.M)
    failures = re.findall(r'^Tests failed: (\d+)$', stderr, re.M)
    todos = re.findall(r'^Number of todos: (.*)$', stdout, re.M)
    passed = (execution['exit_code'] == 0 and not execution['timed_out']
              and actual == expected and counts == ['253'] and failures == ['0'] and todos == ['12'])
    return {'passed': passed, 'expected_count':253, 'recorded_counts':counts,
            'exact_case_sequence': actual == expected, 'missing_cases':sorted(set(expected)-set(actual)),
            'unexpected_cases':sorted(set(actual)-set(expected)), 'reported_failures':failures,
            'todos':todos, 'todo_assertions_are_known_limitations':True}


def run_phase(source, output, name, argv, seconds):
    started = time.monotonic(); before = resource.getrusage(resource.RUSAGE_CHILDREN)
    timed_out = False; code = None; error = None; process = None; cleanup = None
    try:
        with (output/(name+'.stdout')).open('xb') as out, (output/(name+'.stderr')).open('xb') as err:
            env = {'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(output),'TMPDIR':str(output)}
            process = subprocess.Popen(argv,cwd=source,stdout=out,stderr=err,env=env,start_new_session=True)
            try:
                code = process.wait(timeout=seconds-3)
            except subprocess.TimeoutExpired:
                timed_out = True; os.killpg(process.pid,signal.SIGTERM)
                try: code = process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL); code = process.wait(timeout=1)
    except Exception as exc:
        error = type(exc).__name__ + ': ' + str(exc)
    finally:
        if process is not None:
            # A exited parent does not imply its descendants exited. This group
            # was created exclusively for this phase; never target another group.
            try:
                os.killpg(process.pid, signal.SIGKILL)
                cleanup = 'remaining_group_killed'
            except ProcessLookupError:
                cleanup = 'group_absent'
            except OSError as exc:
                cleanup = 'cleanup_failed: ' + str(exc)
                error = error or cleanup
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                error = error or 'owned_parent_not_reaped'
            if cleanup == 'remaining_group_killed':
                error = error or 'owned_descendants_outlived_parent'
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    receipt = {'argv':argv,'exit_code':code,'timed_out':timed_out,'error':error,
               'cleanup':cleanup,'wall_seconds':time.monotonic()-started,'budget_seconds':seconds,
               'user_seconds':after.ru_utime-before.ru_utime,'system_seconds':after.ru_stime-before.ru_stime,
               'children_cumulative_maxrss_kib':after.ru_maxrss}
    for stream in ('stdout','stderr'):
        p=output/(name+'.'+stream)
        receipt[stream+'_sha256']=digest(p.read_bytes()) if p.exists() else None
    (output/(name+'.json')).write_text(json.dumps(receipt,sort_keys=True)+'\n')
    return receipt


def run(source, output):
    source=source.absolute(); output=output.absolute()
    if output.resolve().is_relative_to(source.resolve()):
        raise ValueError('owned_output_inside_source')
    for executable, sha in ((COMPILER,COMPILER_SHA256),(MAKE,MAKE_SHA256)):
        if digest(executable.read_bytes()) != sha:
            raise ValueError('owned_build_tool_identity')
    if any(source.rglob('*.o')) or any((source/n).exists() for n in ('cppcheck','testrunner')):
        raise ValueError('owned_clean_build_required')
    expected = {**PRODUCTION_SOURCE_SHA256, **AFTER_SHA256, 'lib/nico_stage_counters.h':HEADER_SHA256}
    for name, sha in expected.items():
        if digest(read_regular(source/name)) != sha:
            raise ValueError('owned_composed_source_identity')
    target=source/'test/testsimplifytemplate.cpp'
    updated=apply_fixture(read_regular(target),read_regular(ROOT/'owned-fixtures.patch'))
    expected_names()
    output.mkdir()  # Exclusive evidence; never overwrite a prior attempt.
    target.write_bytes(updated)  # Explicit private test-only modification, kept for review.
    argv=[str(MAKE),'-B','-j2','CXX='+str(COMPILER),'MATCHCOMPILER=yes','FILESDIR=/opt/cppcheck','CXXFLAGS=-O2 -DNDEBUG',
          'TESTOBJ=test/fixture.o test/helpers.o test/main.o test/options.o test/testsimplifytemplate.o',
          'cppcheck','testrunner']
    build=run_phase(source,output,'build',argv,300)
    result={'build':build,'passed':False,'assessed_execution':False,'source_sha256':expected,
            'fixture_sha256':AFTER_TEST_SHA256,'patch_sha256':PATCH_SHA256,
            'compiler_sha256':COMPILER_SHA256,'compiler_version':'14.2.0',
            'make_sha256':MAKE_SHA256,'clean_build_required':True}
    try:
        if build['exit_code']==0 and not build['timed_out'] and build['error'] is None:
            result['binary_sha256']={n:digest((source/n).read_bytes()) for n in ('cppcheck','testrunner')}
            execution=run_phase(source,output,'tests',['./testrunner','TestSimplifyTemplate'],180)
            result['execution']=execution
            result['verdict']=verdict((output/'tests.stdout').read_text(errors='replace'),
                                      (output/'tests.stderr').read_text(errors='replace'),execution)
            result['passed']=result['verdict']['passed'] and execution['error'] is None
        else:
            result['tests_not_run']=expected_names()
    except Exception as exc:
        result['error']=type(exc).__name__+': '+str(exc)
        result['passed']=False
        if 'execution' not in result:
            result['tests_not_run']=expected_names()
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute-owned',action='store_true',required=True)
    args=parser.parse_args()
    raise SystemExit(0 if run(args.source,args.output)['passed'] else 1)


if __name__ == '__main__':
    main()
