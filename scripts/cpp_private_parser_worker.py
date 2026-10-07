"""Minimal retained-input loading extension for the unchanged reviewed AST diagnostic.

Runs only in the fixed isolated diagnostic container.  Runtime inputs are actual
retained compiler/dependency/generated/header evidence, not replacement analysis.
Historical receipts, run/artifact selection and credentials are not mounted.
"""
import argparse
import base64
import hashlib
import json
import os

import importlib.machinery, importlib.util
from pathlib import Path
import sys
import time
import types

sys.dont_write_bytecode = True
ORIGINAL_SHA = 'daad27799550a82955bdc69a3b067ce0722fb8669e25527d40298173b0bac417'
MAX_MEMBER = 64 * 1024 * 1024
MAX_RECEIPT = 8 * 1024 * 1024



class _VerifiedBufferLoader(importlib.machinery.SourceFileLoader):
    """Import one already verified source buffer, never cached bytecode."""
    def __init__(self, name, path, raw):
        super().__init__(name, str(path))
        self.verified_raw = raw

    def get_data(self, path):
        if path != self.path:
            raise OSError('verified_source_bytecode_unavailable')
        return self.verified_raw

    def set_data(self, path, data, **kwargs):
        # No bytecode cache or source mutation is part of this diagnostic.
        return None


def _import_verified_buffer(path, raw, label, namespace=None):
    loader = _VerifiedBufferLoader(label, path, raw)
    spec = importlib.util.spec_from_loader(label, loader)
    module = importlib.util.module_from_spec(spec)
    if namespace is not None:
        module.__dict__.update(namespace)
    loader.exec_module(module)
    return module

def require(ok, code):
    if not ok:
        raise ValueError(code)


def original_module():
    path = Path(__file__).resolve().with_name('cpp_same_image_dependency_diagnostic.py')
    raw = path.read_bytes()
    require(len(raw) == 18904 and hashlib.sha256(raw).hexdigest() == ORIGINAL_SHA,
            'unchanged_complete_diagnostic_source')
    return _import_verified_buffer(path, raw, 'unchanged_reviewed_ast_diagnostic')


def retained_inputs(subject, root, pins):
    require(pins.get('schema') == 'nico.runtime.same_image_parser_pins.v1', 'runtime_pins_schema')
    root = root.absolute()
    require(root.resolve(strict=True) == root, 'runtime_input_root')
    expected = {subject.safe_path(row['path']): row for row in pins['runtime_members']}
    require(len(pins['runtime_members']) == len(expected) == 3
            and set(expected) == {'compiler.json', 'snapshot.json', 'input-manifest.json'},
            'minimal_runtime_member_population')
    actual = set()
    for directory, directories, files in os.walk(root, followlinks=False):
        require(all(not (Path(directory) / name).is_symlink() for name in directories),
                'runtime_directory_symlink')
        actual.update((Path(directory) / name).relative_to(root).as_posix() for name in files)
    require(actual == set(expected), 'minimal_runtime_actual_population')
    bodies = {}
    for name, row in expected.items():
        bodies[name] = subject.regular(root / name, MAX_MEMBER, row['sha256'], row['bytes'])
    manifest = subject.decode(bodies['input-manifest.json'])
    compiler = subject.decode(bodies['compiler.json'])
    snapshot = subject.decode(bodies['snapshot.json'])
    require(manifest.get('schema') == 'nico.runtime.retained_parser_inputs.v1', 'runtime_manifest_schema')
    targets = manifest['targets']
    require(len(targets) == 3031 and subject.sha(subject.canonical(targets)) ==
            manifest['target_population_sha256'] == pins['frozen_target']['target_population_sha256'],
            'retained_frozen_target_population')
    require(len(compiler['records']) == 577 and len(snapshot['files']) == 143
            and len(snapshot['generated_units']) == 42, 'bound_raw_input_population')
    metadata = {}
    captured = 0
    for name, row in snapshot['files'].items():
        body = base64.b64decode(row['base64'], validate=True)
        require(len(body) == row['bytes'] and subject.sha(body) == row['sha256'], 'raw_snapshot_file_binding')
        metadata[name] = {'bytes': row['bytes'], 'sha256': row['sha256']}
        captured += len(body)
    require(metadata == manifest['generated_files'] and captured == snapshot['captured_bytes']
            and snapshot['file_population_sha256'] == manifest['snapshot_population_sha256'],
            'retained_snapshot_metadata_binding')
    request = {'targets': targets, 'generated_files': metadata}
    dependencies, retained = [], []
    for index, row in enumerate(compiler['records']):
        if row['dependency_bytes']:
            body = base64.b64decode(row['dependency_bytes'], validate=True)
            require(subject.sha(body) == row['dependency_sha256'], 'raw_dependency_binding')
            dependencies.append((index, body))
            retained.append((row['source_dependencies'], row['generated_dependencies'], row['toolchain_dependencies']))
    require(len(dependencies) == 576, 'retained_nonempty_dependency_list_population')
    dummy = base64.b64decode(snapshot['files']['dummy_cxx_source.cpp']['base64'], validate=True)
    require(dummy == b'#error', 'genuine_generated_error_input_changed')
    return request, dependencies, retained, {
        'runtime_members_verified': 3, 'target_digest_population': 3031,
        'raw_compiler_records': 577, 'snapshot_files': 143, 'generated_units': 42,
        'nonempty_dependency_lists': 576, 'fallback_obligations_executed': 0,
        'snapshot_header_dependencies_verified': snapshot['header_dependencies_verified'],
        'genuine_dummy_error_retained': True,
        'host_original_32_member_and_provider_zip_verification_required': True,
        'historical_selection_or_receipt_metadata_mounted': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', required=True, type=Path)
    parser.add_argument('--pins', required=True, type=Path)
    args = parser.parse_args()
    subject = original_module()
    sys.addaudithook(subject.audit)
    pins_raw = subject.regular(args.pins, MAX_RECEIPT)
    pins = subject.decode(pins_raw)
    require(pins['diagnostic_script_sha256'] == ORIGINAL_SHA, 'original_diagnostic_pin')
    result = {'schema': 'nico.private.runtime_parser_diagnostic.v1', 'status': 'UNPROVEN',
              'production_qualified': False, 'target_execution': False, 'native_execution': False,
              'analyzer_execution': False, 'assessed_compiler_execution': False,
              'full_producer_sequence_executed': False, 'full_native_qualified': False,
              'module_or_PROGRAM_executed': False, 'diagnostic_container_executed': False,
              'historical_image_recovered': False, 'pins_sha256': subject.sha(pins_raw), 'timings': [],
              'required_full_obligations_unchanged': {'contexts': 577, 'fallback_contexts': 576,
                                                     'full_headers_and_generated_inputs': True},
              'execution_wall_limit_seconds': 480, 'historical001f_measurement': False}
    try:
        result['environment'] = subject.environment(pins)
        result['diagnostic_container_executed'] = True
        (before, after), fixtures = subject.scopes(pins)
        request, dependencies, retained, provenance = retained_inputs(subject, args.inputs, pins)
        result['input_provenance'] = provenance
        unchanged = subject.sha(subject.canonical(request)), subject.sha(subject.canonical(
            [(index, subject.sha(raw)) for index, raw in dependencies]))
        values = []
        for variant, function in [('baseline', before), ('candidate', after)]:
            start, cpu = time.perf_counter_ns(), time.process_time_ns()
            outputs = [function(raw, request) for index, raw in dependencies]
            result['timings'].append({'variant': variant, 'dependency_lists': len(dependencies),
                                     'wall_ms': (time.perf_counter_ns() - start) / 1e6,
                                     'process_cpu_ms': (time.process_time_ns() - cpu) / 1e6})
            values.append(outputs)
        require(values[0] == values[1] == retained, 'actual_retained_helper_outputs_changed')
        require(unchanged == (subject.sha(subject.canonical(request)), subject.sha(subject.canonical(
            [(index, subject.sha(raw)) for index, raw in dependencies]))), 'actual_inputs_mutated')
        result.update(status='SAME_IMAGE_AST_HELPERS_VERIFIED',
                      outputs_sha256=subject.sha(subject.canonical(values[0])),
                      actual_retained_outputs_identical=True, original_inputs_unchanged=True,
                      fixture_checks=subject.controls(before, after, fixtures), fixture_pairs=41,
                      individual_fixture_calls=82,
                      timing_limitations='One baseline-then-candidate sequence with the same process, image, request '
                      'and retained dependency bytes; preparation untimed, cache state unknown; no original-cold, '
                      'analyzer, whole-parent, stage-allocation, complete validator or qualification claim.')
        peak = subject.regular('/sys/fs/cgroup/memory.peak', 1024).decode().strip()
        require(peak.isdecimal() and int(peak) <= 12884901888, 'memory_peak_bound')
        result['memory_peak_bytes_including_untimed_preparation_and_controls'] = int(peak)
    except BaseException as error:
        result.update(status='UNPROVEN', error_type=type(error).__name__)
        raise
    finally:
        result['forbidden_events'] = subject.EVENTS
        raw = subject.canonical(result) + b'\n'
        require(len(raw) <= MAX_RECEIPT, 'compact_private_receipt_bound')
        sys.stdout.buffer.write(raw)


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        # The attached driver captures this private receipt; no traceback or URL.
        sys.exit(1)
