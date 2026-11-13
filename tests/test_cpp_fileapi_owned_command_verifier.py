"""Owned verifier regressions from the actual 37264033490:1 GCC command.

These tests replay command metadata; they do not execute CMake or qualify a worker.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def runner():
    path = Path(__file__).parent / 'fixtures/cpp/fileapi-export-off-owned-control/run_fileapi_control.py'
    spec = importlib.util.spec_from_file_location('owned_fileapi_command_verifier', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def inputs():
    source, build = Path('/owned/source'), Path('/owned/build')
    compiler = '/usr/bin/x86_64-linux-gnu-gcc-13'
    target = {'name': 'hidden', 'id': 'hidden-owned',
              'sources': [{'path': 'hidden.c', 'compileGroupIndex': 0}],
              'compileGroups': [{'sourceIndexes': [0], 'language': 'C',
                                 'languageStandard': {'standard': '11'},
                                 'defines': [{'define': 'SOURCE_SENTINEL=19'}, {'define': 'TARGET_SENTINEL=17'}],
                                 'includes': [{'path': str(source / 'include')}, {'path': str(build / 'generated')}],
                                 'compileCommandFragments': [{'fragment': '-g -Wextra -std=gnu11'}]}]}
    native = [compiler, '-DTARGET_SENTINEL=17', '-DSOURCE_SENTINEL=19',
              '-I' + str(source / 'include'), '-I' + str(build / 'generated'),
              '-g', '-std=gnu11', '-Wextra', '-MD', '-MT', 'CMakeFiles/hidden.dir/hidden.c.o',
              '-MF', 'CMakeFiles/hidden.dir/hidden.c.o.d', '-o', 'CMakeFiles/hidden.dir/hidden.c.o',
              '-c', str(source / 'hidden.c')]
    return source, build, compiler, target, native


@pytest.mark.parametrize('fileapi_reversed', [False, True])
@pytest.mark.parametrize('native_reversed', [False, True])
def test_owned_distinct_defines_accept_either_order(runner, inputs, fileapi_reversed, native_reversed):
    source, build, compiler, target, native = inputs
    if fileapi_reversed:
        target['compileGroups'][0]['defines'].reverse()
    if native_reversed:
        native[1:3] = reversed(native[1:3])
    settings = runner.validate_hidden(target, target, source, build)
    assert runner.validate_native_command(native, settings, compiler) == ['-g', '-std=gnu11', '-Wextra']


@pytest.mark.parametrize('mutation', [
    'duplicate_define', 'changed_define', 'missing_define', 'extra_define',
    'reversed_includes', 'changed_compiler', 'changed_flag', 'duplicate_flag',
    'changed_dependency_target', 'changed_dependency_file', 'changed_object', 'changed_source', 'extra_tail',
])
def test_owned_native_mutations_rejected(runner, inputs, mutation):
    source, build, compiler, target, native = inputs
    settings = runner.validate_hidden(target, target, source, build)
    if mutation == 'duplicate_define': native[2] = native[1]
    elif mutation == 'changed_define': native[1] = '-DTARGET_SENTINEL=18'
    elif mutation == 'missing_define': del native[1]
    elif mutation == 'extra_define': native.insert(3, '-DFOREIGN=1')
    elif mutation == 'reversed_includes': native[3:5] = reversed(native[3:5])
    elif mutation == 'changed_compiler': native[0] = '/foreign/gcc'
    elif mutation == 'changed_flag': native[5] = '-O2'
    elif mutation == 'duplicate_flag': native[6] = native[5]
    elif mutation == 'changed_dependency_target': native[10] += '-changed'
    elif mutation == 'changed_dependency_file': native[12] += '-changed'
    elif mutation == 'changed_object': native[14] += '-changed'
    elif mutation == 'changed_source': native[16] = str(source / 'main.c')
    elif mutation == 'extra_tail': native.append('-DFOREIGN=1')
    with pytest.raises(ValueError):
        runner.validate_native_command(native, settings, compiler)


@pytest.mark.parametrize('mutation', ['duplicate_define', 'changed_define', 'extra_define', 'reversed_includes'])
def test_owned_fileapi_mutations_rejected(runner, inputs, mutation):
    source, build, _, original, _ = inputs
    target = copy.deepcopy(original)
    group = target['compileGroups'][0]
    if mutation == 'duplicate_define': group['defines'][1] = group['defines'][0]
    elif mutation == 'changed_define': group['defines'][0] = {'define': 'SOURCE_SENTINEL=20'}
    elif mutation == 'extra_define': group['defines'].append({'define': 'FOREIGN=1'})
    elif mutation == 'reversed_includes': group['includes'].reverse()
    with pytest.raises(ValueError):
        runner.validate_hidden(target, target, source, build)
