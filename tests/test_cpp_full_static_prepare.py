"""Owned inert adapter guards; no provider, Docker, analyzer or target calls."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import tempfile
import types
import unittest

# The whole reviewed public source is checked before module execution. These
# controls never call prepare(), invoke(), providers, Docker or target tools.
import ast
import linecache

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / 'scripts/cpp_full_static_prepare.py'
EXPECTED_PREPARE_SHA = '130d5515b35cb04d745c2c2e45d05f8c0594fd0b621e4e091200d762dcd7c494'
SOURCE_RAW = SOURCE.read_bytes()
if hashlib.sha256(SOURCE_RAW).hexdigest() != EXPECTED_PREPARE_SHA:
    raise AssertionError('reviewed_prepare_source_digest')
SUBJECT = types.ModuleType('generic_static_prepare_under_review')
SUBJECT.__file__ = str(SOURCE)
linecache.cache[str(SOURCE)] = (len(SOURCE_RAW), None, SOURCE_RAW.decode().splitlines(True), str(SOURCE))
exec(compile(SOURCE_RAW, str(SOURCE), 'exec'), SUBJECT.__dict__)
RUNNER_PATH = REPO_ROOT / 'scripts/cpp_static_runner_scope.py'
EXPECTED_SELECTED_SCOPE_SHA = '4bf6c5fc0fb1d2c576793fc283ed1c80a4f7f5026f23cb5e19affcd7e84c7ff0'
RUNNER = SUBJECT.module_from_verified_buffer(RUNNER_PATH, EXPECTED_SELECTED_SCOPE_SHA,
                                             'owned_selected_14_definition_context')
HEAD, PREPARER = 'a' * 40, 'b' * 64


def transport_fixture():
    image, tar = 'sha256:' + 'c' * 64, 'd' * 64
    records = {'schema': 'nico.private.runtime_preparation.v1', 'status': 'PRIVATE_RETAINED_INPUTS_PREPARED',
               'source': {'commit': HEAD}, 'adapter_sha256': PREPARER,
               'recipe_source': {'commit': SUBJECT.RECIPE_HEAD, 'tree': SUBJECT.RECIPE_TREE, 'tracked_files': 3305},
               'decoded_provider_raw_zip_not_old_local_annotation': True, 'target_or_native_execution': False,
               'historical_exact_image_replay_satisfied': False,
               'required_full_obligations_unchanged': {'contexts': 577, 'fallback_contexts': 576,
                                                     'full_headers_and_generated_inputs': True},
               'downloads': {'baseline': {'provider_raw_zip_verified': True, 'bytes': 100, 'sha256': 'e' * 64}},
               'provider_records': {'baseline': {'size_in_bytes': 100, 'digest': 'sha256:' + 'e' * 64}},
               'complete_archive_proof': {'config_id': image, 'archive': {'sha256': tar, 'bytes': 300},
                                         'all_layer_diffids_verified': True,
                                         'safe_unique_outer_regular_or_directory_members': True}}
    pins = {'schema': 'nico.c34.same_image_parser_diagnostic_input_pins.v1',
            'recipe_source': deepcopy(records['recipe_source']),
            'baseline': {'members': [{'path': 'owned/' + str(i) + '.txt', 'bytes': 5,
                                     'sha256': SUBJECT.sha(b'owned')} for i in range(32)]},
            'image': {'image_config_id': image, 'tar_sha256': tar, 'tar_bytes': 300}}
    return records, pins


def set_path(mapping, path, value):
    for key in path[:-1]:
        mapping = mapping[key]
    mapping[path[-1]] = value


def policy_fixture():
    stage = types.SimpleNamespace(STAGE_EXECUTION_SECONDS=1020, STAGE_WALL_SECONDS=1030,
                                  LIMITS={'wall_seconds': 540, 'case_seconds': 90, 'parallel': 4},
                                  STAGE_BUDGET={'limits_share_execution_envelope': True})
    fallback = types.SimpleNamespace(LOW_CONTENTION_LIMITS={'wall_seconds': 480, 'case_seconds': 120, 'parallel': 2})
    resource = {key: RUNNER.LIMITS[key] for key in ('cpus', 'memory_bytes', 'pids', 'tmpfs_bytes')}
    capacity = types.SimpleNamespace(BASELINE_QUALIFICATION_PROFILE='owned', resources_for=lambda _: resource)
    return stage, capacity, fallback, resource


class Controls(unittest.TestCase):
    def test_selected_14_definition_scope_and_guard_source(self):
        raw = RUNNER_PATH.read_bytes()
        self.assertEqual(SUBJECT.sha(raw), EXPECTED_SELECTED_SCOPE_SHA)
        definitions = [row.name for row in ast.parse(raw).body
                       if isinstance(row, (ast.FunctionDef, ast.ClassDef))]
        self.assertEqual(definitions, ['Rejected', 'require', 'sha', 'canonical', 'git_blob', 'git_tree',
            'safe_path', 'regular', 'strict_json', 'VerifiedLoader', 'VerifiedFinder',
            'verify_target_source', 'compact_stage', 'invoke'])
        self.assertFalse(hasattr(RUNNER, 'prepare'))
        self.assertFalse(hasattr(RUNNER, 'bind_library'))
        self.assertEqual(RUNNER.FLAGS, {'extended_compiler_budget': True, 'compiler_environment': True,
                                     'header_provenance': True, 'collect_completed_compiler_failures': True})
        self.assertEqual(RUNNER.LIMITS['stage_execution_seconds'], 1020)
        self.assertEqual(RUNNER.LIMITS['stage_wall_seconds'], 1030)
        self.assertIsNotNone(RUNNER.invoke)
        self.assertIsNotNone(RUNNER.verify_target_source)
        # Selected buffers in a new context, not whole historical runner execution,
        # a new invocation, or a repeated 22-control pass.

    def test_verified_buffer_executes_same_bytes_and_rejects_changed_source_first(self):
        raw = b'owned_marker = 7\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'owned.py'
            path.write_bytes(raw)
            module = SUBJECT.module_from_verified_buffer(path, SUBJECT.sha(raw), 'owned_only')
            self.assertEqual(module.owned_marker, 7)
            path.write_bytes(raw + b'raise RuntimeError("unverified-owned-source")\n')
            with self.assertRaisesRegex(SUBJECT.PreparationRejected, '^file_digest$'):
                SUBJECT.module_from_verified_buffer(path, SUBJECT.sha(raw), 'must_not_execute')

    def test_current_supported_transport_positive(self):
        records, pins = transport_fixture()
        SUBJECT.assert_current_transport(records, pins, expected_operation=HEAD, expected_preparer=PREPARER)

    def test_current_transport_binding_scope_and_population_negatives(self):
        cases = [('records', ['source', 'commit'], '0' * 40, 'current_transport_operation_binding'),
                 ('records', ['adapter_sha256'], '0' * 64, 'current_transport_operation_binding'),
                 ('records', ['status'], 'UNPROVEN', 'prepared_transport_schema'),
                 ('records', ['recipe_source', 'tree'], '0' * 40, 'prepared_recipe_binding'),
                 ('pins', ['recipe_source', 'tracked_files'], 3304, 'prepared_recipe_binding'),
                 ('records', ['decoded_provider_raw_zip_not_old_local_annotation'], False, 'transport_scope'),
                 ('records', ['target_or_native_execution'], True, 'transport_scope'),
                 ('records', ['historical_exact_image_replay_satisfied'], True, 'transport_scope'),
                 ('records', ['required_full_obligations_unchanged', 'contexts'], 576, 'transport_obligations'),
                 ('records', ['required_full_obligations_unchanged', 'fallback_contexts'], 575, 'transport_obligations'),
                 ('records', ['required_full_obligations_unchanged', 'full_headers_and_generated_inputs'], False, 'transport_obligations'),
                 ('records', ['downloads', 'baseline', 'provider_raw_zip_verified'], False, 'current_provider_zip_receipt'),
                 ('records', ['downloads', 'baseline', 'bytes'], True, 'current_provider_zip_receipt'),
                 ('records', ['downloads', 'baseline', 'sha256'], '0' * 64, 'current_provider_zip_receipt'),
                 ('records', ['complete_archive_proof', 'config_id'], 'sha256:' + '0' * 64, 'prepared_complete_image_binding'),
                 ('records', ['complete_archive_proof', 'archive', 'sha256'], '0' * 64, 'prepared_complete_image_binding'),
                 ('records', ['complete_archive_proof', 'all_layer_diffids_verified'], False, 'prepared_complete_image_binding')]
        for scope, path, value, error in cases:
            with self.subTest(scope=scope, path=path):
                records, pins = transport_fixture()
                set_path(records if scope == 'records' else pins, path, value)
                with self.assertRaisesRegex(SUBJECT.PreparationRejected, '^' + error + '$'):
                    SUBJECT.assert_current_transport(records, pins, expected_operation=HEAD, expected_preparer=PREPARER)
        for population in ('duplicate', 'missing'):
            records, pins = transport_fixture()
            if population == 'duplicate':
                pins['baseline']['members'][-1] = deepcopy(pins['baseline']['members'][0])
            else:
                pins['baseline']['members'].pop()
            with self.subTest(population=population), self.assertRaisesRegex(SUBJECT.PreparationRejected, '^decoded32_unique_population$'):
                SUBJECT.assert_current_transport(records, pins, expected_operation=HEAD, expected_preparer=PREPARER)

    def test_decoded_members_reject_extra_bytes_changed_file_and_symlink(self):
        for mutation, error in [('none', None), ('extra', 'decoded32_actual_population'),
                                ('changed', 'file_digest'), ('symlink', 'decoded_member_type')]:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                path = root / 'owned.txt'; path.write_bytes(b'owned')
                rows = [{'path': 'owned.txt', 'sha256': SUBJECT.sha(b'owned'), 'bytes': 5}]
                if mutation == 'extra':
                    (root / 'extra.txt').write_bytes(b'extra')
                elif mutation == 'changed':
                    path.write_bytes(b'other')
                elif mutation == 'symlink':
                    (root / 'link').symlink_to(path)
                if error:
                    with self.assertRaisesRegex(SUBJECT.PreparationRejected, '^' + error + '$'):
                        SUBJECT.verify_decoded_members(RUNNER, root, rows)
                else:
                    SUBJECT.verify_decoded_members(RUNNER, root, rows)

    def test_actual_git_entries_build_hash_bound_source_map_without_old_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); (root / 'nico').mkdir()
            bodies = {'nico/owned.py': b'owned = True\n', 'readme.txt': b'owned\n'}
            listing = bytearray()
            for name, raw in bodies.items():
                path = root / name; path.write_bytes(raw); path.chmod(0o644)
                listing.extend(b'100644 blob ' + RUNNER.git_blob(raw).encode() + b'\t' + name.encode() + b'\0')
            entries, sources = SUBJECT.source_map_from_listing(RUNNER, root, bytes(listing), 2)
            self.assertEqual(set(entries), set(bodies))
            self.assertEqual(set(sources), {'nico/owned.py'})
            self.assertEqual(sources['nico/owned.py'][1], SUBJECT.sha(bodies['nico/owned.py']))
            for altered, error in [(bytes(listing) + bytes(listing).split(b'\0')[0] + b'\0', 'recipe_git_entry'),
                                   (bytes(listing).replace(b'100644 blob', b'120000 blob', 1), 'recipe_git_entry'),
                                   (bytes(listing).replace(RUNNER.git_blob(bodies['nico/owned.py']).encode(), b'0' * 40, 1), 'recipe_blob_bytes')]:
                with self.assertRaisesRegex(SUBJECT.PreparationRejected, '^' + error + '$'):
                    SUBJECT.source_map_from_listing(RUNNER, root, altered, 2)
            (root / 'nico/owned.py').chmod(0o755)
            with self.assertRaisesRegex(SUBJECT.PreparationRejected, '^recipe_mode$'):
                SUBJECT.source_map_from_listing(RUNNER, root, bytes(listing), 2)

    def test_original_policy_and_resources_unchanged_with_negative_controls(self):
        stage, capacity, fallback, resource = policy_fixture()
        SUBJECT.assert_policy(RUNNER, stage, capacity, fallback)
        for key, value in [('STAGE_EXECUTION_SECONDS', 1021), ('STAGE_WALL_SECONDS', 1031),
                           ('LIMITS', {'wall_seconds': 541, 'case_seconds': 90, 'parallel': 4}),
                           ('LIMITS', {'wall_seconds': 540, 'case_seconds': 91, 'parallel': 4}),
                           ('LIMITS', {'wall_seconds': 540, 'case_seconds': 90, 'parallel': 3}),
                           ('STAGE_BUDGET', {'limits_share_execution_envelope': False})]:
            stage, capacity, fallback, resource = policy_fixture()
            setattr(stage, key, value)
            with self.subTest(key=key), self.assertRaisesRegex(SUBJECT.PreparationRejected, '^unchanged_static_policy$'):
                SUBJECT.assert_policy(RUNNER, stage, capacity, fallback)
        for key, value in [('cpus', '8'), ('memory_bytes', RUNNER.LIMITS['memory_bytes'] + 1),
                           ('pids', '512'), ('tmpfs_bytes', RUNNER.LIMITS['tmpfs_bytes'] + 1)]:
            stage, capacity, fallback, resource = policy_fixture()
            resource[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(SUBJECT.PreparationRejected, '^unchanged_native_resources$'):
                SUBJECT.assert_policy(RUNNER, stage, capacity, fallback)
        for limits in [{'wall_seconds': 481, 'case_seconds': 120, 'parallel': 2},
                       {'wall_seconds': 480, 'case_seconds': 121, 'parallel': 2},
                       {'wall_seconds': 480, 'case_seconds': 120, 'parallel': 1}]:
            stage, capacity, fallback, resource = policy_fixture(); fallback.LOW_CONTENTION_LIMITS = limits
            with self.assertRaisesRegex(SUBJECT.PreparationRejected, '^unchanged_static_policy$'):
                SUBJECT.assert_policy(RUNNER, stage, capacity, fallback)

    def test_baseline_overlay_and_guard_negative_bindings(self):
        entries = {'nico/assessment_cpp_project_compiler.py': {'sha256': SUBJECT.BASELINE_COMPILER_SHA,
                   'git_blob': '0' * 40, 'bytes': 1}, 'nico/assessment_cpp_clang_fallback.py':
                   {'sha256': SUBJECT.GUARD_SHA, 'git_blob': SUBJECT.GUARD_BLOB}}
        sources = {'nico/assessment_cpp_project_compiler.py': (Path('/owned'), SUBJECT.BASELINE_COMPILER_SHA)}
        selected = SUBJECT.compiler_overlay(RUNNER, entries, sources, Path('/unused-owned'), 'baseline')
        self.assertEqual(selected['kind'], 'unchanged_recipe_baseline')
        for path, value, error in [(['nico/assessment_cpp_project_compiler.py', 'sha256'], '0' * 64, 'recipe_compiler_baseline'),
                                    (['nico/assessment_cpp_clang_fallback.py', 'sha256'], '0' * 64, 'f091_guard_binding'),
                                    (['nico/assessment_cpp_clang_fallback.py', 'git_blob'], '0' * 40, 'f091_guard_binding')]:
            changed = deepcopy(entries); set_path(changed, path, value)
            with self.assertRaisesRegex(SUBJECT.PreparationRejected, '^' + error + '$'):
                SUBJECT.compiler_overlay(RUNNER, changed, dict(sources), Path('/unused-owned'), 'baseline')
        with self.assertRaisesRegex(SUBJECT.PreparationRejected, '^compiler_variant$'):
            SUBJECT.compiler_overlay(RUNNER, entries, sources, Path('/unused-owned'), 'shrunk-obligations')

    def test_candidate_overlay_exact_existing_source_bytes_and_mutation_rejected(self):
        candidate = Path(os.environ.get('NICO_STATIC_COMPILER_CANDIDATE',
                            str(REPO_ROOT / 'nico/assessment_cpp_project_compiler.py'))).resolve()
        raw = candidate.read_bytes()
        self.assertEqual(SUBJECT.sha(raw), SUBJECT.CANDIDATE_COMPILER_SHA)
        entries = {'nico/assessment_cpp_project_compiler.py': {'sha256': SUBJECT.BASELINE_COMPILER_SHA,
                   'git_blob': '0' * 40, 'bytes': 1}, 'nico/assessment_cpp_clang_fallback.py':
                   {'sha256': SUBJECT.GUARD_SHA, 'git_blob': SUBJECT.GUARD_BLOB}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); path = root / 'nico/assessment_cpp_project_compiler.py'
            path.parent.mkdir(); path.write_bytes(raw)
            sources = {}
            selected = SUBJECT.compiler_overlay(RUNNER, entries, sources, root, 'candidate')
            self.assertEqual(selected['git_blob'], SUBJECT.CANDIDATE_COMPILER_BLOB)
            self.assertEqual(sources['nico/assessment_cpp_project_compiler.py'][1], SUBJECT.CANDIDATE_COMPILER_SHA)
            path.write_bytes(raw + b'\n# owned-byte-mutation\n')
            with self.assertRaisesRegex(SUBJECT.PreparationRejected, '^file_digest$'):
                SUBJECT.compiler_overlay(RUNNER, entries, {}, root, 'candidate')


    def test_receipt_row_anchor_type_bound_and_actual_regular_size(self):
        # Execute only the guard expression from the SHA-bound prepare function,
        # with owned rows. No retained receipt, library or prepare call is used.
        tree = ast.parse(SOURCE_RAW)
        prepare = next(row for row in tree.body
                       if isinstance(row, ast.FunctionDef) and row.name == 'prepare')
        guards = [row for row in prepare.body if isinstance(row, ast.Expr)
                  and isinstance(row.value, ast.Call)
                  and isinstance(row.value.func, ast.Name) and row.value.func.id == 'require'
                  and len(row.value.args) == 2 and isinstance(row.value.args[1], ast.Constant)
                  and row.value.args[1].value == 'trusted_transport_receipt_member_binding']
        self.assertEqual(len(guards), 1)
        guard = compile(ast.fix_missing_locations(ast.Module(body=guards, type_ignores=[])),
                        '<sha-bound-receipt-row-guard>', 'exec')
        anchor = SUBJECT.sha(b'owned')
        def check(row):
            scope = {'receipt_ref': row, 'receipt_anchor': anchor, 'MAX_FILE': SUBJECT.MAX_FILE,
                     'require': SUBJECT.require, 'type': type, 'int': int}
            exec(guard, scope)
        for length in (1, 5, SUBJECT.MAX_FILE):
            with self.subTest(length=length):
                check({'sha256': anchor, 'bytes': length})
        for length in (True, False, 0, -1, SUBJECT.MAX_FILE + 1, 5.0, '5', None):
            with self.subTest(length=length), self.assertRaisesRegex(
                    SUBJECT.PreparationRejected, '^trusted_transport_receipt_member_binding$'):
                check({'sha256': anchor, 'bytes': length})
        with self.assertRaisesRegex(SUBJECT.PreparationRejected,
                                    '^trusted_transport_receipt_member_binding$'):
            check({'sha256': '0' * 64, 'bytes': 5})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'owned-receipt.json'
            path.write_bytes(b'owned')
            self.assertEqual(SUBJECT.regular(path, digest=anchor, size=5), b'owned')
            for length in (1, SUBJECT.MAX_FILE, True):
                with self.subTest(actual_size=length), self.assertRaisesRegex(
                        SUBJECT.PreparationRejected, '^file_length$'):
                    SUBJECT.regular(path, digest=anchor, size=length)
            path.write_bytes(b'other')
            with self.assertRaisesRegex(SUBJECT.PreparationRejected, '^file_digest$'):
                SUBJECT.regular(path, digest=anchor, size=5)

if __name__ == '__main__':
    unittest.main()
