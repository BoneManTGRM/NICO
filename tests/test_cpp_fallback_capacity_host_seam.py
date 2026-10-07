"""Owned inert host-boundary controls; never call Git, Docker, target code or providers."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


SOURCE = pathlib.Path(__file__).parents[1] / 'scripts/cpp_same_image_full_static_diagnostic.py'
SPEC = importlib.util.spec_from_file_location('owned_capacity_host_seam', SOURCE)
CALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CALLER)


class HostInputControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name).resolve()
        self.directory = self.root / 'host/capacity-sample'
        self.directory.mkdir(parents=True, mode=0o700)
        self.arguments = types.SimpleNamespace(prepared_inputs=self.root)
        self.mapping = {}
        for key in ('environment', 'primary', 'fallback'):
            raw = (key + '\n').encode()
            self.mapping[key] = {'file': key + '.json', 'bytes': len(raw),
                                 'sha256': hashlib.sha256(raw).hexdigest()}
            (self.directory / (key + '.json')).write_bytes(raw)
        self.patcher = patch.object(CALLER, 'SAMPLE_INPUTS', self.mapping)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.addCleanup(self.temp.cleanup)

    def test_exact_three_hash_bound_files_are_accepted_as_bytes(self):
        inputs, references = CALLER.sample_inputs(self.arguments)
        self.assertEqual(set(inputs), {'environment', 'primary', 'fallback'})
        self.assertEqual(references['primary']['sha256'], self.mapping['primary']['sha256'])

    def test_corrupt_primary_is_rejected(self):
        (self.directory / 'primary.json').write_bytes(b'corrupt\n')
        with self.assertRaises(CALLER.CallerRejected):
            CALLER.sample_inputs(self.arguments)

    def test_missing_fallback_is_rejected(self):
        (self.directory / 'fallback.json').unlink()
        with self.assertRaises(CALLER.CallerRejected):
            CALLER.sample_inputs(self.arguments)

    def test_extra_input_is_rejected(self):
        (self.directory / 'request.json').write_bytes(b'{}')
        with self.assertRaises(CALLER.CallerRejected):
            CALLER.sample_inputs(self.arguments)

    def test_symlink_input_is_rejected(self):
        original = self.directory / 'primary.json'
        body = original.read_bytes()
        outside = self.root / 'outside.json'
        outside.write_bytes(body)
        original.unlink()
        original.symlink_to(outside)
        with self.assertRaises(CALLER.CallerRejected):
            CALLER.sample_inputs(self.arguments)

    def test_public_sample_directory_is_rejected(self):
        self.directory.chmod(0o755)
        with self.assertRaises(CALLER.CallerRejected):
            CALLER.sample_inputs(self.arguments)


class FullRequestBeforeSelectionControls(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.primary_request = {'contexts': [{'context_id': str(i)} for i in range(577)],
            'generated_files': {str(i): {'sha256': 'a' * 64} for i in range(143)}}
        self.full_request = {'contexts': [{'index': i, 'context_id': str(i), 'invocation': ['clang', str(i)],
            'dropped_arguments': [], 'source_dependencies': {'x.cpp': 'a' * 64},
            'generated_dependencies': {'x.h': 'b' * 64}} for i in range(576)],
            'schema': 'nico.cpp-clang-fallback-request.v7', 'required_contexts': [str(i) for i in range(577)],
            'primary_analyzed_contexts': [str(i) for i in range(479)],
            'header_source_targets': {str(i): 'a' * 64 for i in range(3031)},
            'header_generated_files': self.primary_request['generated_files'],
            'limits': {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2}}
        self.environment = {'image_config_digest': CALLER.FIXED_IMAGE}
        self.prepared = {'database': b'db', 'targets': {'x.cpp': 'a' * 64}, 'snapshot': {},
                         'compiler_raw': b'compiler', 'summary': {'flags': True}}
        self.inputs = {'environment': b'environment', 'primary': b'primary', 'fallback': b'fallback'}
        self.mutations = None
        self.sample = types.SimpleNamespace(select_sample=self.select)

        def observed(name, result):
            def call(*args, **kwargs):
                self.events.append(name)
                return result
            return call
        modules = {}
        for name in ('nico', 'nico.assessment_cpp_project_compiler', 'nico.assessment_cpp_static_environment',
                     'nico.assessment_cpp_project_static', 'nico.assessment_cpp_clang_fallback'):
            modules[name] = types.ModuleType(name)
        modules['nico'].__path__ = []
        modules['nico.assessment_cpp_project_compiler'].project_compiler_request = observed('compiler_request', {'contexts': 577})
        modules['nico.assessment_cpp_static_environment'].environment_request = observed('environment_request', {'requested_image': CALLER.FIXED_IMAGE})
        modules['nico.assessment_cpp_static_environment'].validate_environment = observed('validate_environment', self.environment)
        modules['nico.assessment_cpp_project_static'].project_static_request = observed('primary_request', self.primary_request)
        modules['nico.assessment_cpp_project_static'].validate_project_static = observed('validate_primary', {'required_contexts': 577})
        modules['nico.assessment_cpp_clang_fallback'].clang_fallback_request = observed('full_fallback_request', self.full_request)
        patcher = patch.dict(sys.modules, modules)
        patcher.start()
        self.addCleanup(patcher.stop)

    def select(self, request, raw, *, expected_fallback_sha256, prepared_summary):
        self.events.append('select_four')
        self.assertEqual(len(request['contexts']), 576)
        self.assertEqual(raw, b'fallback')
        self.assertEqual(expected_fallback_sha256, CALLER.SAMPLE_INPUTS['fallback']['sha256'])
        selected = copy.deepcopy(request)
        selected['contexts'] = [copy.deepcopy(request['contexts'][i]) for i in CALLER.SAMPLE_INDICES]
        if self.mutations:
            self.mutations(selected)
        return selected, {'full_request_sha256': CALLER.sha(CALLER.canonical(request))}

    def test_full_request_validators_precede_selection_and_exact_bindings_are_retained(self):
        primary, selected, binding, proof = CALLER.reconstruct_sample_request(self.prepared, self.inputs, self.sample)
        self.assertEqual(self.events, ['compiler_request', 'environment_request', 'validate_environment',
            'primary_request', 'validate_primary', 'full_fallback_request', 'select_four'])
        self.assertEqual([c['index'] for c in selected['contexts']], [0, 58, 154, 186])
        self.assertEqual(proof['full_header_source_population'], 3031)
        self.assertEqual(proof['full_header_generated_population'], 143)
        self.assertEqual(proof['full_fallback_request_sha256'], binding['full_request_sha256'])
        self.assertTrue(proof['no_primary_native_execution'])

    def test_wrong_image_rejected_before_selection(self):
        self.environment['image_config_digest'] = 'sha256:' + '0' * 64
        with self.assertRaises(CALLER.CallerRejected):
            CALLER.reconstruct_sample_request(self.prepared, self.inputs, self.sample)
        self.assertNotIn('select_four', self.events)

    def test_partial_full_population_rejected_before_selection(self):
        self.full_request['contexts'].pop()
        with self.assertRaises(CALLER.CallerRejected):
            CALLER.reconstruct_sample_request(self.prepared, self.inputs, self.sample)
        self.assertNotIn('select_four', self.events)

    def test_cap_change_rejected_before_selection(self):
        self.full_request['limits']['wall_seconds'] = 481
        with self.assertRaises(CALLER.CallerRejected):
            CALLER.reconstruct_sample_request(self.prepared, self.inputs, self.sample)
        self.assertNotIn('select_four', self.events)

    def test_selected_argv_change_rejected(self):
        self.mutations = lambda selected: selected['contexts'][0]['invocation'].append('-DNICO_REPAIR')
        with self.assertRaises(CALLER.CallerRejected):
            CALLER.reconstruct_sample_request(self.prepared, self.inputs, self.sample)

    def test_selected_dependency_change_rejected(self):
        self.mutations = lambda selected: selected['contexts'][0]['source_dependencies'].clear()
        with self.assertRaises(CALLER.CallerRejected):
            CALLER.reconstruct_sample_request(self.prepared, self.inputs, self.sample)

    def test_selected_full_header_inventory_change_rejected(self):
        self.mutations = lambda selected: selected['header_source_targets'].clear()
        with self.assertRaises(CALLER.CallerRejected):
            CALLER.reconstruct_sample_request(self.prepared, self.inputs, self.sample)

    def test_selected_order_change_rejected(self):
        self.mutations = lambda selected: selected['contexts'].reverse()
        with self.assertRaises(CALLER.CallerRejected):
            CALLER.reconstruct_sample_request(self.prepared, self.inputs, self.sample)


class SourcePathAndModeControls(unittest.TestCase):
    EXPECTED = (
        'nico/assessment_cpp_clang_fallback.py',
        'nico/assessment_cpp_project_compiler.py',
        'nico/assessment_cpp_compiler_evidence.py',
        'nico/assessment_cpp_generated_context.py',
        'nico/assessment_cpp_clang_header_evidence.py',
        'nico/assessment_cpp_project_snapshot.py',
    )

    def owned_sources(self, root):
        arguments = types.SimpleNamespace(operation_source=root / 'operation', recipe_source=root / 'recipe')
        expected = {}
        for name in self.EXPECTED:
            directory = arguments.operation_source if name.endswith('project_compiler.py') else arguments.recipe_source
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            expected[name] = ('owned-inert-' + name).encode()
            path.write_bytes(expected[name])
        return arguments, expected

    def test_exact_six_real_source_paths_are_read_from_the_correct_roots(self):
        with tempfile.TemporaryDirectory() as temporary:
            arguments, expected = self.owned_sources(pathlib.Path(temporary).resolve())
            self.assertEqual(CALLER.sample_source_buffers(arguments), expected)

    def test_original_wrong_path_cannot_be_substituted(self):
        with tempfile.TemporaryDirectory() as temporary:
            arguments, expected = self.owned_sources(pathlib.Path(temporary).resolve())
            wrong = tuple(name.replace('assessment_cpp_compiler_evidence.py',
                                       'assessment_cpp_project_evidence.py') for name in self.EXPECTED)
            with patch.object(CALLER, 'SAMPLE_SOURCE_PATHS', wrong), self.assertRaises(FileNotFoundError):
                CALLER.sample_source_buffers(arguments)

    def test_sample_source_hash_without_sample_mode_rejects_before_pair_dispatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary).resolve()
            arguments = types.SimpleNamespace(**{name:root / name for name in
                ('operation_source','recipe_source','prepared_inputs','target_checkout','output','dependency_proof')})
            for name in ('expected_caller_sha256','expected_scope_sha256','expected_prepare_sha256',
                         'expected_preparer_sha256','expected_exporter_sha256','expected_proof_sha256'):
                setattr(arguments, name, 'a' * 64)
            arguments.expected_sample_sha256 = 'b' * 64
            arguments.fallback_capacity_sample = None
            with self.assertRaisesRegex(CALLER.CallerRejected, '^sample_source_without_sample_mode$'):
                CALLER.normalize(arguments)


if __name__ == '__main__':
    unittest.main()
