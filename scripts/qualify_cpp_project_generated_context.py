"""Native owned controls for project snapshots; never production or Bitcoin proof."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

from nico.assessment_cpp_configuration_probe import probe_project_configuration
from nico.assessment_cpp_project_snapshot import validate_project_snapshot
from nico.assessment_worker_receipts import canonical_bytes
from scripts.qualify_cpp_project_configuration import persist_project_artifact


def fixture(root, negative=False, static_diagnostic=False):
    """Two contexts of one original, a generated source and a generated header."""
    files = {
        'CMakeLists.txt': '''cmake_minimum_required(VERSION 3.22)
project(nico_generated_owned LANGUAGES C CXX)
option(BUILD_TESTS "Owned native test" ON)
configure_file(config.h.in include/config.h COPYONLY)
configure_file(unused.h.in include/unused.h COPYONLY)
configure_file(generated.cpp.in generated/generated.cpp COPYONLY)
include_directories(${CMAKE_CURRENT_BINARY_DIR}/include)
add_library(first OBJECT repeated.cpp)
target_compile_definitions(first PRIVATE VARIANT=1)
add_library(second OBJECT repeated.cpp)
target_compile_definitions(second PRIVATE VARIANT=2)
add_library(generated STATIC ${CMAKE_CURRENT_BINARY_DIR}/generated/generated.cpp)
add_executable(owned main.cpp $<TARGET_OBJECTS:first> $<TARGET_OBJECTS:second>)
target_link_libraries(owned PRIVATE generated)
if(BUILD_TESTS)
    enable_testing()
    add_test(NAME owned_generated COMMAND owned)
endif()
''',
        'repeated.cpp': '''#if VARIANT == 1
int first(){return 1;}
#else
int second(){return 2;}
#endif
''',
        'main.cpp': 'int first(); int second(); int generated();\nint main(){return first()+second()+generated()==45 ? 0 : 1;}\n',
        'config.h.in': '#define GENERATED_VALUE 42\n',
        'unused.h.in': '#define OWNED_UNUSED_HEADER 1\n',
        'generated.cpp.in': '#include "config.h"\nint generated(){return GENERATED_VALUE;}\n',
    }
    if static_diagnostic:
        # Deliberate owned analyzer diagnostic; never invoked by the native test.
        files['generated.cpp.in'] += 'int owned_static_diagnostic(){int value;return value;}\n'
    if negative:
        files['CMakeLists.txt'] += 'file(CREATE_LINK "${CMAKE_CURRENT_SOURCE_DIR}/config.h.in" "${CMAKE_CURRENT_BINARY_DIR}/rejected.h" SYMBOLIC)\n'
    root.mkdir()
    for name, text in files.items():
        (root / name).write_text(text, encoding='utf-8')
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(files)}


def qualify(image, output, project_static_analysis=False, extended_compiler_budget=False):
    output.mkdir(parents=True, exist_ok=True)
    evidence = {'schema': 'nico.cpp-generated-project-control.v1', 'status': 'UNPROVEN',
        'synthetic_owned_control': True, 'production_qualified': False,
        'bitcoin_executed': False, 'controls': []}
    def save():
        data = canonical_bytes(evidence)
        if len(data) > 16 * 1024 * 1024:
            raise ValueError('qualification_control_evidence_budget')
        path = output / 'receipt.json.tmp'
        with path.open('wb') as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(path, output / 'receipt.json')
    save()
    try:
        with tempfile.TemporaryDirectory(prefix='nico-generated-owned-') as temporary:
            cases = ([('clean', False, False)] if project_static_analysis else [])
            cases += [('positive', False, project_static_analysis), ('negative', True, project_static_analysis)]
            for name, negative, diagnostic in cases:
                root = Path(temporary) / name
                targets = fixture(root, negative, static_diagnostic=diagnostic)
                directory = output / name; directory.mkdir(exist_ok=True)
                row = {'name': name, 'source_targets': targets, 'configuration': None, 'baseline': None}
                evidence['controls'].append(row); save()
                def keep_configuration(value):
                    row['configuration'] = value; save()
                configured = probe_project_configuration(root, targets, image,
                    project_options={'BUILD_TESTS': 'ON'}, retain=keep_configuration)
                if configured['status'] != 'CONFIGURATION_CAPTURED':
                    raise ValueError('qualification_control_configure_unproven')
                execution = {'schema': 'nico.cpp-baseline-execution.v1',
                    'profile': 'cpp-baseline-qualification-v1',
                    'compilation_database_sha256': configured['compilation_database_sha256'],
                    'build_seconds': 60, 'test_seconds': 30, 'test_case_seconds': 15, 'parallel': 2}
                def keep_baseline(value):
                    row['baseline'] = value; save()
                result = probe_project_configuration(root, targets, image,
                    project_options={'BUILD_TESTS': 'ON'}, baseline_execution=execution,
                    capture_generated_context=True, project_compiler_evidence=True,
                    project_static_analysis=project_static_analysis, retain=keep_baseline,
                    extended_compiler_budget=extended_compiler_budget,
                    retain_artifact=lambda key, raw: persist_project_artifact(directory, key, raw))
                if (not result['compiled'] or not result['tests_passed'] or not result['cleanup_verified']
                        or result['tests_discovered'] != ['owned_generated']
                        or result['configured_invocations'] != 4
                        or result['configured_translation_units'] != ['main.cpp', 'repeated.cpp']
                        or result['configured_generated_units'] != ['generated/generated.cpp']):
                    raise ValueError('qualification_control_baseline_unproven')
                if negative:
                    if (result['status'] != 'UNPROVEN' or result['generated_context_verified']
                            or result['error'] != 'worker_configuration_probe_snapshot_failed'):
                        raise ValueError('qualification_control_negative_unproven')
                    op = next(op for op in result['operations'] if op['id'] == 'project-generated-context')
                    raw = (directory / op['output_artifact']['path']).read_bytes()
                    if (hashlib.sha256(raw).hexdigest() != op['output_sha256']
                            or json.loads(raw).get('error') != 'worker_generated_project_header_type_invalid'):
                        raise ValueError('qualification_control_negative_reason_unproven')
                else:
                    if result['status'] != 'BASELINE_EXECUTED' or not result['generated_context_verified']:
                        raise ValueError('qualification_control_snapshot_unproven')
                    ref = result['generated_context']['artifact']
                    raw = (directory / ref['path']).read_bytes()
                    if len(raw) != ref['bytes'] or hashlib.sha256(raw).hexdigest() != ref['sha256']:
                        raise ValueError('qualification_control_artifact_mismatch')
                    snapshot = validate_project_snapshot(json.loads(raw), result['compilation_contexts'])
                    expected = {'generated/generated.cpp': targets['generated.cpp.in'],
                                'include/config.h': targets['config.h.in'],
                                'include/unused.h': targets['unused.h.in']}
                    if {p: v['sha256'] for p, v in snapshot['files'].items()} != expected:
                        raise ValueError('qualification_control_generated_bytes_mismatch')
                    compiler = result['project_compiler']
                    if (not compiler or not compiler['complete'] or len(compiler['checked_contexts']) != 4
                            or 'include/config.h' not in compiler['generated_header_inclusions']
                            or 'include/unused.h' not in compiler['unvisited_generated_headers']
                            or compiler['static_analysis_executed'] or compiler['object_code_generated']
                            or compiler['production_qualified']):
                        raise ValueError('qualification_control_compiler_unproven')
                    if project_static_analysis:
                        static = result['project_static']
                        if (not static or not static['complete'] or len(static['analyzed_contexts']) != 4
                                or (diagnostic and not any(f['rule_id'] == 'uninitvar' and f['origin'] == 'generated'
                                           and f['path'] == 'generated/generated.cpp' for f in static['findings']))
                                or (not diagnostic and static['findings'])
                                or not result['project_static_stage']['complete']
                                or static['human_review_completed'] or static['production_qualified']):
                            raise ValueError('qualification_control_static_unproven')
                    if snapshot['header_dependencies_verified'] or snapshot['analysis_executed']:
                        raise ValueError('qualification_control_false_analysis')
                row['expected_outcome_verified'] = True; save()
        evidence['status'] = 'OWNED_SNAPSHOT_CONTROLS_PASSED'
    finally:
        save()
        print(json.dumps({'status': evidence['status'], 'production_qualified': False, 'bitcoin_executed': False}))
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--project-static-analysis', action='store_true')
    parser.add_argument('--extended-compiler-budget', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('cpp-generated-context-qualification'))
    args = parser.parse_args()
    qualify(args.image, args.output, project_static_analysis=args.project_static_analysis,
            extended_compiler_budget=args.extended_compiler_budget)


if __name__ == '__main__':
    main()
