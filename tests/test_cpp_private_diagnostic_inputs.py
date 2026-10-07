"""Owned inert controls: no network, Docker, image, analyzer or target execution."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/cpp_private_diagnostic_inputs.py'
SPEC = importlib.util.spec_from_file_location('private_transport_under_review', SOURCE)
SUBJECT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUBJECT)


class Response(io.BytesIO):
    def __init__(self, code, body=b'', location=None):
        super().__init__(body)
        self.code = code
        self.headers = {} if location is None else {'Location': location}


class Opener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request.full_url, dict(request.header_items()), timeout))
        return self.responses.pop(0)


def owned_artifact(body=b'owned-by-negative-controls'):
    return {'id': 7, 'name': 'owned', 'expired': False, 'expires_at': '2099-01-01T00:00:00Z',
            'size_in_bytes': len(body), 'digest': 'sha256:' + hashlib.sha256(body).hexdigest(),
            'archive_download_url': SUBJECT.API + '/repos/' + SUBJECT.REPOSITORY + '/actions/artifacts/7/zip'}


def owned_run(identity=2):
    return {'id': identity, 'path': SUBJECT.BASELINE_WORKFLOW, 'head_branch': SUBJECT.BASELINE_BRANCH,
            'head_sha': 'a' * 40, 'event': 'pull_request', 'status': 'completed', 'conclusion': 'failure',
            'run_attempt': 1, 'repository': {'id': 9}, 'head_repository': {'id': 9}}


class CatalogClient:
    def __init__(self, rows):
        self.rows = rows

    def json(self, path):
        if '/attempts/1' in path:
            return self.rows[0]
        return {'total_count': len(self.rows), 'workflow_runs': self.rows}


class Controls(unittest.TestCase):
    def reject(self, call, *args, **kwargs):
        with self.assertRaises(SUBJECT.PreparationError):
            call(*args, **kwargs)

    def test_trusted_suffix_and_credentials(self):
        for url in ['https://productionresultssa18.blob.core.windows.net/actions-results/owned.zip?q=owned',
                    'https://owned.blob.core.windows.net/owned']:
            self.assertEqual(SUBJECT.safe_transport_url(url), url)
        for url in ['http://owned.blob.core.windows.net/x', 'https://evilblob.core.windows.net/x',
                    'https://owned.blob.core.windows.net.evil/x', 'https://owned.blob.core.windows.net:444/x',
                    'https://user@owned.blob.core.windows.net/x', 'https://@owned.blob.core.windows.net/x',
                    'https://owned.blob.core.windows.net/x#fragment', 'https://127.0.0.1/x']:
            self.reject(SUBJECT.safe_transport_url, url)

    def test_credential_stripped_after_api_redirect(self):
        raw = b'owned-by-negative-controls'
        client = SUBJECT.ActionsClient('owned-fake-token')
        opener = Opener([Response(302, location='https://owned.blob.core.windows.net/owned'), Response(200, raw)])
        client._opener = opener
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'input.zip'
            result = client.download(owned_artifact(raw), output, 1024)
            self.assertTrue(result['provider_raw_zip_verified'])
            self.assertEqual(output.read_bytes(), raw)
        self.assertEqual(opener.calls[0][1]['Authorization'], 'Bearer owned-fake-token')
        self.assertNotIn('Authorization', opener.calls[1][1])
        self.assertNotIn('owned-fake-token', json.dumps(result))

    def test_redirect_count_and_wrong_origin_rejected(self):
        for responses in [[Response(302, location='https://evil.example/owned')],
                          [Response(302, location='https://owned.blob.core.windows.net/a'),
                           Response(302, location='https://owned.blob.core.windows.net/b'),
                           Response(302, location='https://owned.blob.core.windows.net/c')]]:
            client = SUBJECT.ActionsClient('owned-fake-token')
            client._opener = Opener(responses)
            with tempfile.TemporaryDirectory() as directory:
                self.reject(client.download, owned_artifact(), Path(directory) / 'input.zip', 1024)

    def test_digest_size_and_expiry_rejected(self):
        for field, value in [('digest', 'sha256:' + '0' * 64), ('size_in_bytes', 3)]:
            raw = b'owned-by-negative-controls'
            record = owned_artifact(raw)
            record[field] = value
            client = SUBJECT.ActionsClient('owned-fake-token')
            client._opener = Opener([Response(200, raw)])
            with tempfile.TemporaryDirectory() as directory:
                self.reject(client.download, record, Path(directory) / 'input.zip', 1024)
        for field, value in [('expired', True), ('expires_at', '2000-01-01T00:00:00Z'),
                             ('digest', None), ('size_in_bytes', True), ('expires_at', 'not-a-date')]:
            record = owned_artifact()
            record[field] = value
            self.reject(SUBJECT.artifact_digest, record, 1024)

    def test_unique_exact_run_no_latest_wins(self):
        result = SUBJECT.select_run(CatalogClient([owned_run()]), SUBJECT.BASELINE_WORKFLOW,
                                    SUBJECT.BASELINE_BRANCH, 'pull_request', 'failure', 9, head='a' * 40)
        self.assertEqual(result['id'], 2)
        for rows in [[], [owned_run(2), owned_run(3)]]:
            self.reject(SUBJECT.select_run, CatalogClient(rows), SUBJECT.BASELINE_WORKFLOW,
                        SUBJECT.BASELINE_BRANCH, 'pull_request', 'failure', 9, head='a' * 40)
        for field, value in [('head_sha', 'b' * 40), ('head_branch', 'other'), ('run_attempt', 2),
                             ('event', 'push'), ('conclusion', 'success'), ('path', 'other')]:
            row = owned_run()
            row[field] = value
            self.assertFalse(SUBJECT.run_identity(row, SUBJECT.BASELINE_WORKFLOW, SUBJECT.BASELINE_BRANCH,
                                                  'pull_request', 'failure', 9, head='a' * 40))

    def test_incomplete_catalog_rejected(self):
        self.reject(SUBJECT.bounded_catalog, {'total_count': 101, 'workflow_runs': []}, 'workflow_runs')
        self.reject(SUBJECT.bounded_catalog, {'total_count': 2, 'workflow_runs': [owned_run()]}, 'workflow_runs')

    def test_artifact_unique_and_exact_run_binding(self):
        row = owned_artifact()
        row['workflow_run'] = {'id': 2, 'head_sha': 'a' * 40, 'head_branch': SUBJECT.BASELINE_BRANCH,
                               'repository_id': 9, 'head_repository_id': 9}
        class Client:
            def __init__(self, records):
                self.records = records
            def json(self, path):
                return {'total_count': len(self.records), 'artifacts': self.records}
        self.assertEqual(SUBJECT.select_artifact(Client([row]), owned_run(), 'owned', 9, 1024)['id'], 7)
        for records in [[], [row, row]]:
            self.reject(SUBJECT.select_artifact, Client(records), owned_run(), 'owned', 9, 1024)
        for key, value in [('id', 8), ('head_sha', 'b' * 40), ('head_repository_id', 8)]:
            changed = dict(row, workflow_run=dict(row['workflow_run'], **{key: value}))
            self.reject(SUBJECT.select_artifact, Client([changed]), owned_run(), 'owned', 9, 1024)

    def test_whole_worker_mutation_is_rejected_before_execution(self):
        raw = b'def inputs():\n    return 1\n'
        name = 'scripts/cpp_same_image_dependency_diagnostic.py'
        with tempfile.TemporaryDirectory() as directory, patch.object(SUBJECT, 'SOURCE_PINS',
                {name: hashlib.sha256(raw).hexdigest()}):
            root = Path(directory)
            path = root / name
            path.parent.mkdir()
            path.write_bytes(raw)
            self.assertEqual(SUBJECT.verified_source_bodies(root)[name], raw)
            # The decoder AST remains the same; a new top-level effect must not be executed.
            path.write_bytes(raw + b'raise RuntimeError("owned-mutation")\n')
            self.reject(SUBJECT.verified_source_bodies, root)

    def test_duplicate_omit_inventory_and_private_umask(self):
        SUBJECT.exact_inventory_paths([{'path': 'a'}, {'path': 'b'}], {'a': {}, 'b': {}})
        self.reject(SUBJECT.exact_inventory_paths, [{'path': 'a'}, {'path': 'a'}], {'a': {}, 'b': {}})
        with tempfile.TemporaryDirectory() as directory:
            old = os.umask(0o077)
            try:
                path = Path(directory) / 'owned.json'
                SUBJECT.write_private(path, {'owned': True})
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                runtime = Path(directory) / 'runtime'
                result = SUBJECT.runtime_write(runtime, 'scripts/owned.txt', b'owned')
                self.assertEqual(stat.S_IMODE(result.stat().st_mode), 0o644)
                self.assertEqual(stat.S_IMODE(result.parent.stat().st_mode), 0o755)
                self.assertEqual(stat.S_IMODE(runtime.stat().st_mode), 0o755)
            finally:
                os.umask(old)

    def test_retained_copy_cannot_self_pin_changed_bytes(self):
        raw = b'owned-retained-input'
        ref = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        self.assertEqual(SUBJECT.retained_copy(raw, ref), raw)
        self.reject(SUBJECT.retained_copy, raw + b'x', ref)
        self.reject(SUBJECT.retained_copy, b'x' * len(raw), ref)

    def test_receipt_source_image_and_attempt_binding(self):
        run = dict(owned_run(), verified_tree='b' * 40)
        recipe = {'commit': 'c' * 40, 'tree': 'd' * 40,
                  'tracked_byte_blob_mode_inventory_sha256': 'e' * 64}
        receipt = {'status': 'OWNED', 'production_qualified': False, 'historical_image_recovered': False,
                   'target_execution': False, 'image_config_id': 'sha256:' + 'f' * 64,
                   'operation': {'workflow_head': run['head_sha'], 'workflow_tree': run['verified_tree'],
                                 'run_id': str(run['id']), 'run_attempt': 1, 'helper_sha256': '0' * 64},
                   'recipe_source': dict(recipe, tracked_files=3305),
                   'image_inspection': {'Id': 'sha256:' + 'f' * 64, 'Architecture': 'amd64', 'Os': 'linux'}}
        SUBJECT.verify_receipt_identity(receipt, run, recipe, 'OWNED', '0' * 64)
        for key, value in [('workflow_head', '9' * 40), ('workflow_tree', '9' * 40),
                           ('run_attempt', 2), ('helper_sha256', '9' * 64)]:
            changed = dict(receipt, operation=dict(receipt['operation'], **{key: value}))
            self.reject(SUBJECT.verify_receipt_identity, changed, run, recipe, 'OWNED', '0' * 64)
        changed = dict(receipt, image_inspection=dict(receipt['image_inspection'], Architecture='arm64'))
        self.reject(SUBJECT.verify_receipt_identity, changed, run, recipe, 'OWNED', '0' * 64)

    def test_zip_paths_population_declared_bounds_and_crc(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            good = root / 'good.zip'
            with zipfile.ZipFile(good, 'w') as bundle:
                bundle.writestr('owned/file.txt', b'CONTROL_PAYLOAD')
            rows = SUBJECT.extract_verified_zip(good, root / 'good', 1, 64, 64, {'owned/file.txt'})
            self.assertEqual(rows[0]['sha256'], hashlib.sha256(b'CONTROL_PAYLOAD').hexdigest())
            self.reject(SUBJECT.extract_verified_zip, good, root / 'wrong-count', 2, 64, 64)
            self.reject(SUBJECT.extract_verified_zip, good, root / 'wrong-member-limit', 1, 64, 64,
                        {'owned/file.txt'}, {'owned/file.txt': 4})
            for index, name in enumerate(['../owned', '/owned', 'owned//file', 'owned/./file', 'owned\\file']):
                archive = root / ('bad-' + str(index) + '.zip')
                with zipfile.ZipFile(archive, 'w') as bundle:
                    bundle.writestr(name, b'owned')
                self.reject(SUBJECT.extract_verified_zip, archive, root / ('out-' + str(index)), 1, 64, 64)
            raw = good.read_bytes()
            payload_index = raw.index(b'CONTROL_PAYLOAD')
            damaged = root / 'crc.zip'
            damaged.write_bytes(raw[:payload_index] + b'control_payload'[:15] + raw[payload_index + 15:])
            self.reject(SUBJECT.extract_verified_zip, damaged, root / 'crc', 1, 64, 64)

    def test_zip_duplicate_symlink_and_encryption_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            duplicate = root / 'duplicate.zip'
            with zipfile.ZipFile(duplicate, 'w') as bundle:
                bundle.writestr('owned', b'first')
                bundle.writestr('owned', b'second')
            self.reject(SUBJECT.extract_verified_zip, duplicate, root / 'duplicate', 2, 64, 64)
            linked = root / 'linked.zip'
            info = zipfile.ZipInfo('owned')
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(linked, 'w') as bundle:
                bundle.writestr(info, b'../owned')
            self.reject(SUBJECT.extract_verified_zip, linked, root / 'linked', 1, 64, 64)
            original = root / 'original.zip'
            with zipfile.ZipFile(original, 'w') as bundle:
                bundle.writestr('owned', b'owned')
            raw = bytearray(original.read_bytes())
            raw[6] |= 1
            central = raw.index(b'PK\x01\x02')
            raw[central + 8] |= 1
            encrypted = root / 'encrypted.zip'
            encrypted.write_bytes(raw)
            self.reject(SUBJECT.extract_verified_zip, encrypted, root / 'encrypted', 1, 64, 64)

    def test_json_and_scratch_bounds(self):
        self.reject(SUBJECT.decode, b'{"owned":1,"owned":2}')
        self.reject(SUBJECT.decode, b'{"owned":NaN}')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.reject(SUBJECT.preflight, root, SUBJECT.MAX_SCRATCH + 1, 1)
            self.reject(SUBJECT.preflight, root, 0, 0)


if __name__ == '__main__':
    unittest.main()
