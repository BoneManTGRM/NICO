"""Owned inert caller controls; no target/API/Docker/provider operation.

Written for root review/execution. Guard fixtures are newly owned bytes, not
retained native payloads. These tests never substitute stage or command hooks
into an actual static call and grant no execution/qualification credit.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / 'scripts/cpp_same_image_full_static_diagnostic.py'
SPEC = importlib.util.spec_from_file_location('owned_full_static_caller', SOURCE)
CALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CALLER)


def git_blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


class CallerGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        # Any accidental process or provider-capable execution makes a test fail.
        self.forbidden = patch.object(CALLER.subprocess, 'run', side_effect=AssertionError('no_process_allowed'))
        self.forbidden.start()

    def tearDown(self):
        self.forbidden.stop()
        self.temp.cleanup()

    def owned_file(self, name, raw=b'owned fixture\n', mode=0o400):
        path = self.root / name
        path.write_bytes(raw)
        path.chmod(mode)
        return path

    def row(self, raw, mode='100644'):
        return {'bytes': len(raw), 'sha256': CALLER.sha(raw), 'git_blob': git_blob(raw), 'git_mode': mode}

    def test_regular_positive_exact_owned_bytes(self):
        raw = b'owned fixture\n'
        path = self.owned_file('exact', raw)
        self.assertEqual(CALLER.regular(path, digest=CALLER.sha(raw), size=len(raw)), raw)

    def test_regular_rejects_symlink_and_changed_digest(self):
        path = self.owned_file('original')
        link = self.root / 'link'
        link.symlink_to(path)
        with self.assertRaises(CALLER.CallerRejected):
            CALLER.regular(link)
        with self.assertRaises(CALLER.CallerRejected):
            CALLER.regular(path, digest='0' * 64)

    def test_regular_rejects_size_bool_or_wrong_length(self):
        path = self.owned_file('size', b'a')
        for value in (True, 2):
            with self.subTest(value=value), self.assertRaises(CALLER.CallerRejected):
                CALLER.regular(path, size=value)

    def test_target_member_preserves_nonexec_and_exec_positive(self):
        scope = types.SimpleNamespace(git_blob=git_blob)
        for mode, gitmode in ((0o400, '100644'), (0o500, '100755')):
            raw = b'owned target data only\n'
            path = self.owned_file('mode-' + gitmode, raw, mode)
            self.assertEqual(CALLER.target_member(path, self.row(raw, gitmode), scope), raw)

    def test_target_member_rejects_unexpected_execute(self):
        raw = b'owned nonexecutable data\n'
        path = self.owned_file('unexpected-exec', raw, 0o500)
        with self.assertRaises(CALLER.CallerRejected):
            CALLER.target_member(path, self.row(raw), types.SimpleNamespace(git_blob=git_blob))

    def test_target_member_rejects_group_only_execute(self):
        raw = b'owned executable data\n'
        path = self.owned_file('group-exec', raw, 0o410)
        with self.assertRaises(CALLER.CallerRejected):
            CALLER.target_member(path, self.row(raw, '100755'), types.SimpleNamespace(git_blob=git_blob))

    def test_target_member_rejects_hash_blob_and_mode_mutations(self):
        raw = b'owned target fixture\n'
        path = self.owned_file('changed-identity', raw)
        for field, value in (('sha256', '0' * 64), ('git_blob', '0' * 40), ('git_mode', '120000')):
            row = dict(self.row(raw), **{field: value})
            with self.subTest(field=field), self.assertRaises(CALLER.CallerRejected):
                CALLER.target_member(path, row, types.SimpleNamespace(git_blob=git_blob))

    def proof(self):
        raw = b'{"owned_receipt":true}\n'
        path = self.owned_file('proof.json', raw, 0o600)
        args = types.SimpleNamespace(dependency_proof=path, expected_proof_sha256=CALLER.sha(raw),
                                     expected_proof_bytes=len(raw))
        calls = []
        def gate(proof, verifier, manifest):
            calls.append((proof, verifier, manifest))
            return {'status': 'CURRENT_INSTALLED_DEPENDENCIES_VERIFIED'}
        return args, types.SimpleNamespace(validate_current_receipt=gate), calls

    def test_whole_dependency_proof_positive_calls_exact_pure_gate(self):
        args, verifier, calls = self.proof()
        result = CALLER.dependencies(args, verifier)
        self.assertEqual(calls, [({'owned_receipt': True}, CALLER.VERIFIER_SHA, CALLER.WHEEL_MANIFEST_SHA)])
        self.assertFalse(result['proof_produced_in_this_process'])

    def test_whole_dependency_proof_mutations_prevent_validator(self):
        for field, value in (('expected_proof_sha256', '0' * 64), ('expected_proof_bytes', 1)):
            args, verifier, calls = self.proof()
            setattr(args, field, value)
            with self.subTest(field=field), self.assertRaises(CALLER.CallerRejected):
                CALLER.dependencies(args, verifier)
            self.assertEqual(calls, [])

    def test_dependency_gate_failure_propagates_without_acceptance(self):
        args, verifier, _ = self.proof()
        verifier.validate_current_receipt = lambda *_: CALLER.require(False, 'owned_current_installation_changed')
        with self.assertRaises(CALLER.CallerRejected):
            CALLER.dependencies(args, verifier)

    def test_json_duplicate_and_nonfinite_rejected(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(CALLER.CallerRejected):
                CALLER.decode(raw)

    def test_child_environment_copies_authority_but_no_credentials_or_pythonpath(self):
        environment = {'PATH': '/usr/bin', 'HOME': str(self.root), 'GITHUB_SHA': 'a' * 40,
                       'GITHUB_TOKEN': 'owned-not-a-real-token', 'GH_TOKEN': 'owned-not-a-real-token',
                       'PYTHONPATH': str(self.root), 'UNRELATED_SECRET': 'owned-placeholder'}
        with patch.dict(os.environ, environment, clear=True):
            result = CALLER.child_environment()
        self.assertEqual(result, {name: environment[name] for name in ('PATH', 'HOME', 'GITHUB_SHA')})

    def test_private_receipt_bound_and_exact_digest(self):
        path = self.root / 'receipt.json'
        value = {'status': 'UNPROVEN', 'production_qualified': False}
        ref = CALLER.write_private(path, value)
        raw = path.read_bytes()
        self.assertEqual(ref, {'bytes': len(raw), 'sha256': CALLER.sha(raw)})
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(raw), value)
        with patch.object(CALLER, 'MAX_META', 8), self.assertRaises(CALLER.CallerRejected):
            CALLER.write_private(self.root / 'too-large.json', value)

    def test_current_source_hash_failure_does_not_run_buffer(self):
        path = self.owned_file('pinned-source.py', b'raise AssertionError("must not execute")\n')
        with self.assertRaises(CALLER.CallerRejected):
            CALLER.module_buffer(path, CALLER.regular(path, digest='0' * 64), 'unreachable_owned_buffer')

    def source_fixture(self):
        operation = self.root / 'operation'
        (operation / 'scripts').mkdir(parents=True)
        caller = SOURCE.read_bytes()
        scope = b'# Owned source fixture, never executed\n'
        (operation / 'scripts/caller.py').write_bytes(caller)
        (operation / 'scripts/scope.py').write_bytes(scope)
        prepared = self.root / 'prepared'
        (prepared / 'host').mkdir(parents=True)
        actual = {'commit': 'a' * 40, 'tree': 'b' * 40}
        (prepared / 'host/preparation.json').write_text(json.dumps({'source': actual}))
        paths = {'caller': 'scripts/caller.py', 'scope': 'scripts/scope.py'}
        listing = b''.join(b'100644 blob ' + git_blob(raw).encode() + b'\t' + paths[key].encode() + b'\0'
                           for key, raw in (('caller', caller), ('scope', scope)))
        helper = types.SimpleNamespace(checked_git_source=lambda *_: actual, command=lambda *_a, **_k: listing)
        args = types.SimpleNamespace(operation_source=operation, prepared_inputs=prepared,
            expected_operation='a' * 40, expected_caller_sha256=CALLER.sha(caller),
            expected_scope_sha256=CALLER.sha(scope), expected_prepare_sha256='0' * 64,
            expected_preparer_sha256='0' * 64, expected_exporter_sha256='0' * 64)
        return args, helper, paths, scope

    def test_actual_git_source_buffer_positive(self):
        args, helper, paths, scope = self.source_fixture()
        with patch.object(CALLER, 'SOURCE_PATHS', paths):
            _, rows, buffers = CALLER.source_bindings(args, helper)
        self.assertEqual(buffers['scope'], scope)
        self.assertEqual(rows['scope']['git_blob'], git_blob(scope))

    def test_actual_git_blob_rejects_even_replaced_expected_sha(self):
        args, helper, paths, _ = self.source_fixture()
        changed = b'# Different owned fixture, never executed\n'
        (args.operation_source / paths['scope']).write_bytes(changed)
        args.expected_scope_sha256 = CALLER.sha(changed)
        with patch.object(CALLER, 'SOURCE_PATHS', paths), self.assertRaises(CALLER.CallerRejected):
            CALLER.source_bindings(args, helper)

    def test_failed_preparation_retains_private_cause_without_stage_callback(self):
        output = self.root / 'output'
        context = output / 'context'
        context.mkdir(mode=0o700, parents=True)
        (context / 'cpp_static_runner_scope.py').write_bytes(b'')
        paths = {}
        for key in ('operation_source', 'recipe_source', 'prepared_inputs', 'target_checkout'):
            paths[key] = self.root / key
            paths[key].mkdir(mode=0o700)
        helper_path = paths['operation_source'] / CALLER.SOURCE_PATHS['image_helper']
        helper_path.parent.mkdir()
        helper_raw = b'# Owned inert source bytes\n'
        helper_path.write_bytes(helper_raw)
        proof = self.owned_file('unused-proof.json', b'{}', 0o600)
        arguments = {key: str(value) for key, value in paths.items()}
        arguments.update(output=str(output), dependency_proof=str(proof), expected_operation='a' * 40,
            expected_proof_bytes=2, **{name: '0' * 64 for name in (
                'expected_caller_sha256', 'expected_scope_sha256', 'expected_prepare_sha256',
                'expected_preparer_sha256', 'expected_exporter_sha256', 'expected_proof_sha256')})
        settings = context / 'baseline-settings.json'
        CALLER.write_private(settings, {'schema': 'nico.private.full_static_worker_settings.v1',
            'variant': 'baseline', 'parent_pid': os.getppid(), 'arguments': arguments,
            'source_rows': {}, 'operation': {}})
        fake_scope = types.SimpleNamespace(invoke=lambda *_: self.fail('stage must remain uncalled'))
        def fail_prepare(*_):
            CALLER.require(False, 'owned_preparation_failed')
        def module(_path, _raw, label):
            if label == 'exact_selected_static_scope':
                return fake_scope
            if label == 'exact_generic_prepare':
                return types.SimpleNamespace(prepare=fail_prepare)
            return types.SimpleNamespace()
        with patch.object(CALLER, '__file__', str(context / 'cpp_same_image_full_static_diagnostic.py')), \
             patch.object(CALLER, 'HELPER_SHA', CALLER.sha(helper_raw)), \
             patch.object(CALLER, 'authority', return_value={}), \
             patch.object(CALLER, 'source_bindings', return_value=({}, {}, {'scope': b'', 'prepare': b'', 'verifier': b''})), \
             patch.object(CALLER, 'module_buffer', side_effect=module), \
             patch.object(CALLER, 'dependencies', return_value={'owned_guard_only': True}), \
             self.assertRaises(CALLER.CallerRejected):
            CALLER.worker(settings)
        receipt = json.loads((context / 'runs/baseline/process-receipt.json').read_bytes())
        self.assertEqual(receipt['status'], 'UNPROVEN')
        self.assertEqual(receipt['error'], {'type': 'CallerRejected', 'message': 'owned_preparation_failed'})
        self.assertFalse(receipt['stage_invocation_attempted'])
        self.assertFalse((context / 'runs/baseline/static-stage-receipt.json').exists())
        self.assertFalse((context / 'runs/baseline/diagnostic-result.json').exists())


if __name__ == '__main__':
    unittest.main()
