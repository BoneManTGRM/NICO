"""Regression for omitted C objects in the owned mixed-language control.

The native integration remains the proof for real pinned dependencies. The
local CMake probe uses only owned declarations/header/helper plus a minimal
C++ caller, so it cannot substitute for that dependency/image qualification.
"""
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

import pytest

from scripts.qualify_cpp_full_project_integration import fixture, plan
from scripts.qualify_cpp_full_project_control import FIXTURE


@pytest.mark.parametrize('bounded_fuzz', [False, True])
def test_owned_project_enables_c_for_its_declared_c_translation_unit(bounded_fuzz):
    options = dict(generated_headers=True, project_dependencies=True,
                   project_compiler_options=True, bounded_fuzz=bounded_fuzz)
    files = fixture(**options)
    declaration = re.search(r'^project\(nico_owned_control LANGUAGES ([^)]+)\)$',
                            files['CMakeLists.txt'], re.MULTILINE)
    assert declaration is not None
    assert set(declaration.group(1).split()) == {'C', 'CXX'}
    contract = plan('sha256:' + 'd' * 64, **options)
    assert 'src/library/helper.c' in contract['configuration']['translation_units']
    assert fixture() == FIXTURE
    assert 'LANGUAGES CXX)' in fixture(generated_headers=True,
        project_dependencies=True)['CMakeLists.txt']


@pytest.mark.skipif(not all(shutil.which(x) for x in ('cmake', 'gcc', 'g++', 'make')),
                    reason='owned native CMake probe requires the local toolchain')
def test_actual_cmake_compiles_and_links_the_owned_c_helper(tmp_path):
    """Use the production fixture's project declaration; do not invent C enablement."""
    files = fixture(generated_headers=True, project_dependencies=True,
                    project_compiler_options=True)
    declaration = re.search(r'^project\(nico_owned_control[^\n]+$',
                            files['CMakeLists.txt'], re.MULTILINE).group(0)
    helper = tmp_path / 'helper.c'
    helper.write_text(files['src/library/helper.c'])
    (tmp_path / 'sum.hpp').write_text(files['sum.hpp'])
    (tmp_path / 'main.cpp').write_text('#include "sum.hpp"\n'
        'int main() { return control_identity(42) == 42 ? 0 : 1; }\n')
    (tmp_path / 'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.22)\n'
        + declaration + '\nadd_executable(control main.cpp helper.c)\n')
    build = tmp_path / 'build'
    environment = {'PATH': os.defpath, 'HOME': str(tmp_path), 'TMPDIR': str(tmp_path),
                   'LANG': 'C.UTF-8'}

    def run(args):
        value = subprocess.run(args, cwd=tmp_path, env=environment, capture_output=True,
                               text=True, timeout=20, check=False)
        assert value.returncode == 0, value.stdout + value.stderr
        return value

    run([shutil.which('cmake'), '-S', str(tmp_path), '-B', str(build),
         '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON'])
    database = json.loads((build / 'compile_commands.json').read_text())
    assert {Path(row['file']).name for row in database} == {'helper.c', 'main.cpp'}
    run([shutil.which('cmake'), '--build', str(build), '--parallel', '1'])
    run([str(build / 'control')])


def test_mixed_language_regressions_are_required_before_hosted_native_execution():
    path = Path(__file__).resolve().parents[1] / '.github/workflows/cpp-full-project-integration.yml'
    command = next(line.strip() for line in path.read_text().splitlines()
                   if 'python -m pytest -q tests/test_cpp_fixture_tree.py' in line)
    assert 'tests/test_cpp_mixed_language_activation.py' in shlex.split(command)
