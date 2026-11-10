"""Multipart upload regressions using real parser, evidence, storage and auth.

Only the unchanged upload route and its two response helpers are compiled from
repository-local main.py onto an isolated FastAPI app. This deliberately avoids
full API startup: it is not full production-bootstrap or live-storage coverage.
Normal nico imports and tests/conftest.py remain intact. Every test uses synthetic
credentials, an isolated MemoryAdapter and real temporary upload files.
"""
from __future__ import annotations

import ast
import asyncio
from contextlib import contextmanager
from importlib.metadata import version
import os
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from starlette.datastructures import Headers
import starlette.formparsers as formparsers


BOUNDARY = b'nico_synthetic_upload_boundary_1964'
ADMIN = {'X-NICO-Admin-Token': 'synthetic-local-multipart-regression-admin'}
FIELDS = {'customer_id': 'synthetic-customer', 'project_id': 'synthetic-project', 'run_id': 'synthetic-run'}


def multipart_body(data=b'Synthetic upload only.\n', *, filename='evidence.txt', content_type='text/plain', fields=None, include_file=True, mixed_case=False, file_first=False):
    if fields is None:
        fields = FIELDS
    disposition = b'cOnTeNt-dIsPoSiTiOn' if mixed_case else b'Content-Disposition'
    mime = b'cOnTeNt-TyPe' if mixed_case else b'Content-Type'
    parts = []
    for name, value in fields.items():
        parts.append(disposition + b': form-data; name="' + name.encode() + b'"\r\n\r\n' + value.encode())
    if include_file:
        filename_part = b'' if filename is None else b'; filename="' + filename.encode() + b'"'
        file_part = disposition + b': form-data; name="file"' + filename_part + b'\r\n'
        if content_type is not None:
            file_part += mime + b': ' + content_type.encode() + b'\r\n'
        file_part += b'\r\n' + data
        if file_first:
            parts.insert(0, file_part)
        else:
            parts.append(file_part)
    return b''.join(b'--' + BOUNDARY + b'\r\n' + part + b'\r\n' for part in parts) + b'--' + BOUNDARY + b'--\r\n'


def content_header(*, quoted=False, mixed_media=False):
    boundary = b'"' + BOUNDARY + b'"' if quoted else BOUNDARY
    media = 'Multipart/Form-Data' if mixed_media else 'multipart/form-data'
    return media + '; boundary=' + boundary.decode()


class Chunks(httpx.AsyncByteStream):
    def __init__(self, body, size):
        self.body, self.size, self.read_count = body, size or max(1, len(body)), 0

    async def __aiter__(self):
        for pos in range(0, len(self.body), self.size):
            self.read_count += 1
            yield self.body[pos:pos + self.size]


def request(state, body, *, chunk=0, auth=ADMIN, content_type=None):
    stream = Chunks(body, chunk)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=state['app']), base_url='http://synthetic.invalid') as client:
            return await client.post('/evidence/upload', content=stream, headers={
                **auth, 'Content-Type': content_type or content_header(),
            })

    return asyncio.run(run()), stream


@pytest.fixture
def upload_state_factory(tmp_path):
    # Import normally, after repository conftest and its canonical installers.
    # Do not replace the nico package or reload any production modules.
    from nico import evidence, storage
    import nico.specialist_access_v1 as access

    @contextmanager
    def isolated_state():
        files = []
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv('NICO_ADMIN_TOKEN', ADMIN['X-NICO-Admin-Token'])
            patch.setenv('NICO_COMPREHENSIVE_OPERATOR_PASSWORD',
                         'synthetic-local-multipart-operator')
            patch.delenv('NICO_SARA_OPERATOR_PASSWORD', raising=False)
            patch.delenv('NICO_OPERATOR_SESSION_SIGNING_SECRET', raising=False)
            patch.delenv('DATABASE_URL', raising=False)
            patch.setenv('NICO_DISABLE_POSTGRES', 'true')
            store = storage.Storage()
            assert isinstance(store.adapter, storage.MemoryAdapter)
            assert not store.database_url
            assert store.disable_postgres
            patch.setattr(storage, 'STORE', store)
            patch.setattr(evidence, 'STORE', store)
            patch.setattr(access, '_RATE_LIMITER', type(access._RATE_LIMITER)())

            source = Path(__file__).resolve().parents[1] / 'nico/api/main.py'
            tree = ast.parse(source.read_text(encoding='utf-8'), filename=str(source))
            names = {'safe_operation_result', 'safe_blocked_exception', 'evidence_upload'}
            nodes = [node for node in tree.body
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                     and node.name in names]
            assert len(nodes) == len(names)
            assert {node.name for node in nodes} == names
            app = FastAPI()
            namespace = {
                '__name__': 'repository_upload_route_slice', 'app': app, 'Any': Any,
                'UploadFile': UploadFile, 'File': File, 'Form': Form,
                'HTTPException': HTTPException, 'upload_evidence': evidence.upload_evidence,
            }
            exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
            access.install_specialist_access(app)
            original = formparsers.SpooledTemporaryFile

            def observe_real_file(*args, **kwargs):
                # Retain genuine spooling, restricting each file to pytest's
                # temporary directory without mutating tempfile's global state.
                kwargs.setdefault('dir', tmp_path)
                handle = original(*args, **kwargs)
                files.append(handle)
                return handle

            patch.setattr(formparsers, 'SpooledTemporaryFile', observe_real_file)
            try:
                yield {'files': files, 'store': store, 'app': app, 'evidence_module': evidence}
            finally:
                assert all(handle.closed for handle in files), 'Framework must close real upload files'

    return isolated_state


@pytest.fixture
def state(upload_state_factory):
    with upload_state_factory() as value:
        yield value


def new_records(state):
    return state['store'].list('evidence_items'), state['store'].list('audit_log')


def assert_success(response, state, *, data, filename='evidence.txt', content_type='text/plain', fields=FIELDS):
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'complete'
    assert response.headers['Cache-Control'] == 'no-store, private, max-age=0'
    assert set(response.json()) == {'status', 'scan_id', 'repository', 'customer_id', 'project_id', 'queued'}
    items, audits = new_records(state)
    assert len(items) == len(audits) == 1
    item = items[0]
    assert item['filename'] == (filename or 'upload')
    assert item['size_bytes'] == len(data)
    assert item['content_type'] == content_type
    expected_ids = {'customer_id': fields.get('customer_id', 'default_customer'), 'project_id': fields.get('project_id', 'default_project'), 'run_id': fields.get('run_id', '')}
    assert {key: item[key] for key in expected_ids} == expected_ids
    expected_preview = data.decode('utf-8', errors='replace')[:12000] if content_type in state['evidence_module'].TEXT_TYPES else ''
    assert item['extracted_text_preview'] == expected_preview
    assert audits[0]['action'] == 'evidence.uploaded'
    assert audits[0]['payload'] == {'evidence_id': item['evidence_id'], 'filename': item['filename']}
    assert audits[0]['customer_id'] == expected_ids['customer_id']
    assert audits[0]['project_id'] == expected_ids['project_id']
    assert len(state['files']) == 1
    return item


@pytest.mark.parametrize('chunk', [0, 1, 7, 31])
def test_ordinary_and_split_boundaries(state, chunk):
    data = 'Synthetic café evidence.\nLine two.\n'.encode()
    response, stream = request(state, multipart_body(data), chunk=chunk)
    assert_success(response, state, data=data)
    assert stream.read_count > 0
    assert not state['files'][0]._rolled


def test_quoted_boundary_mixed_header_case_file_first_unicode_fields(state):
    data = 'Synthetic español only.\n'.encode()
    fields = {**FIELDS, 'project_id': 'synthetic-proyecto-café'}
    response, _ = request(state, multipart_body(data, fields=fields, mixed_case=True, file_first=True), chunk=5, content_type=content_header(quoted=True))
    assert_success(response, state, data=data, fields=fields)


@pytest.mark.parametrize('filename,data', [('evidence.txt', b''), ('', b'Synthetic unnamed file.')])
def test_optional_ids_empty_selected_file_and_filename_fallback(state, filename, data):
    response, _ = request(state, multipart_body(data, filename=filename, fields={}), chunk=11)
    assert_success(response, state, data=data, filename=filename, fields={})


def test_browser_no_file_selected_is_missing(state):
    # FastAPI 0.162.0 _is_empty_file treats filename="", size=0 as no selection.
    # This is identical with both multipart versions, not a new regression.
    response, _ = request(state, multipart_body(b'', filename='', fields={}), chunk=11)
    assert response.status_code == 422
    assert response.json() == {'detail': [{'type': 'missing', 'loc': ['body', 'file'], 'msg': 'Field required', 'input': None}]}
    assert new_records(state) == ([], [])


@pytest.mark.parametrize('size', [1024 * 1024 + 17, 20 * 1024 * 1024])
def test_real_spooled_upload_and_exact_application_limit(state, size):
    data = (b'Synthetic spool content.\n' * (size // 25 + 2))[:size]
    assert len(data) == size
    response, _ = request(state, multipart_body(data), chunk=65521)
    assert_success(response, state, data=data)
    assert state['files'][0]._rolled is True


def test_binary_metadata_only(state):
    data = b'%PDF-1.4\n% synthetic parser fixture; not a real document\n'
    response, _ = request(state, multipart_body(data, filename='synthetic.pdf', content_type='application/pdf'), chunk=3)
    item = assert_success(response, state, data=data, filename='synthetic.pdf', content_type='application/pdf')
    assert item['unavailable_data_notes'] == ['PDF text extraction is not enabled in this safe MVP; file metadata is stored only.']


@pytest.mark.parametrize('kind', ['oversized', 'unsupported_type', 'missing_type'])
def test_application_rejection_keeps_storage_and_redaction(state, kind):
    data = b'a' * (20 * 1024 * 1024 + 1) if kind == 'oversized' else b'synthetic only'
    mime = {'oversized': 'text/plain', 'unsupported_type': 'application/octet-stream', 'missing_type': None}[kind]
    response, _ = request(state, multipart_body(data, content_type=mime), chunk=65521)
    assert response.status_code == 400
    assert response.json() == {'detail': {'status': 'blocked', 'code': 'blocked', 'message': 'Request blocked by NICO safety, authorization, or review policy.'}}
    assert new_records(state) == ([], [])
    assert len(state['files']) == 1
    if kind == 'oversized':
        assert state['files'][0]._rolled is True


@pytest.mark.parametrize('kind,expected', [('missing_file', 422), ('missing_filename', 422), ('missing_boundary', 400), ('oversized_text_field', 400)])
def test_parser_and_binding_rejections(state, kind, expected):
    args = {'include_file': kind != 'missing_file', 'filename': None if kind == 'missing_filename' else 'evidence.txt'}
    if kind == 'oversized_text_field':
        args.update(fields={'customer_id': 'x' * (1024 * 1024 + 1)}, file_first=True)
    body = multipart_body(**args)
    response, _ = request(state, body, chunk=65521, content_type='multipart/form-data' if kind == 'missing_boundary' else None)
    assert response.status_code == expected, response.text
    assert new_records(state) == ([], [])
    if kind == 'missing_boundary':
        assert response.json() == {'detail': 'Missing boundary in multipart.'}
    if kind == 'oversized_text_field':
        assert response.json() == {'detail': 'Part exceeded maximum size of 1024KB.'}
        assert len(state['files']) == 1


@pytest.mark.parametrize('auth,expected', [({}, 401), ({'X-NICO-Admin-Token': 'synthetic-wrong'}, 403), ({'X-NICO-Admin-Token': 'synthetic-local-multipart-operator'}, 403), ({'X-NICO-Operator-Session': 'synthetic-not-a-session'}, 403)])
def test_real_authorization_rejects_before_reading_body(state, auth, expected):
    response, stream = request(state, multipart_body(), chunk=1, auth=auth)
    assert response.status_code == expected
    assert response.json()['detail']['code'] == 'site_admin_authentication_required'
    assert response.headers['Cache-Control'] == 'no-store'
    assert stream.read_count == 0
    assert state['files'] == []
    assert new_records(state) == ([], [])


def test_mixed_case_request_media_type(state):
    data = b'Synthetic case normalization.'
    response, _ = request(state, multipart_body(data), chunk=7, content_type=content_header(mixed_media=True))
    # The candidate explicitly corrects media-type case normalization.
    # Only 0.0.32 has the known media-type normalization bug. The declared
    # candidate (0.0.33) and later versions must accept it, never either status.
    expected = 422 if version('python-multipart') == '0.0.32' else 200
    assert response.status_code == expected, response.text
    if expected == 200:
        assert_success(response, state, data=data)
    else:
        assert new_records(state) == ([], [])


@pytest.mark.parametrize('chunk,large', [(1, False), (17, False), (65521, True)])
def test_low_level_parser_preserves_all_binary_bytes_and_closes(state, chunk, large):
    unit = bytes(range(256)) + b'\r\n--nico_synthetic_upload_boundary_196X\r\n'
    data = unit * (4000 if large else 2)
    body = multipart_body(data, filename='bytes.bin', content_type='application/octet-stream')

    async def run():
        parser = formparsers.MultiPartParser(Headers({'Content-Type': content_header()}), Chunks(body, chunk).__aiter__())
        form = await parser.parse()
        try:
            upload = form['file']
            assert await upload.read() == data
            assert upload.size == len(data)
            assert upload.filename == 'bytes.bin'
            assert upload.content_type == 'application/octet-stream'
            assert upload.file._rolled is large
            assert {key: form[key] for key in FIELDS} == FIELDS
        finally:
            await form.close()

    asyncio.run(run())
    assert len(state['files']) == 1
    assert new_records(state) == ([], [])


def test_missing_part_name_closes_previously_created_file(state):
    body = multipart_body(b'synthetic only', fields={})
    closing = b'--' + BOUNDARY + b'--\r\n'
    assert body.endswith(closing)
    body = body[:-len(closing)] + b'--' + BOUNDARY + b'\r\nContent-Disposition: form-data\r\n\r\nmissing name\r\n' + closing
    response, _ = request(state, body, chunk=13)
    assert response.status_code == 400
    assert response.json() == {'detail': 'The Content-Disposition header field "name" must be provided.'}
    assert len(state['files']) == 1
    assert new_records(state) == ([], [])


def test_interrupted_stream_closes_real_spooled_file(state):
    body = multipart_body(b'x' * (1024 * 1024 + 17), fields={})
    closing = b'--' + BOUNDARY + b'--\r\n'
    body = body[:-len(closing)]

    async def interrupted():
        for pos in range(0, len(body), 65521):
            yield body[pos:pos + 65521]
        raise OSError('synthetic interrupted request stream')

    async def run():
        parser = formparsers.MultiPartParser(Headers({'Content-Type': content_header()}), interrupted())
        with pytest.raises(OSError, match='synthetic interrupted request stream'):
            await parser.parse()

    asyncio.run(run())
    assert len(state['files']) == 1
    assert state['files'][0]._rolled is True
    assert state['files'][0].closed
    assert new_records(state) == ([], [])



def test_fixture_restores_environment_storage_parser_and_middleware(upload_state_factory, monkeypatch):
    from nico import evidence, storage
    import nico.specialist_access_v1 as access

    # Distinct synthetic inherited values prove restoration, including values
    # that the upload fixture deliberately unsets. No credentials are read.
    inherited = {
        'NICO_ADMIN_TOKEN': 'synthetic-inherited-admin',
        'NICO_COMPREHENSIVE_OPERATOR_PASSWORD': 'synthetic-inherited-operator',
        'NICO_SARA_OPERATOR_PASSWORD': 'synthetic-inherited-legacy',
        'NICO_OPERATOR_SESSION_SIGNING_SECRET': 'synthetic-inherited-signing-value',
        'DATABASE_URL': 'synthetic-inherited-database-not-a-real-url',
        'NICO_DISABLE_POSTGRES': 'true',
    }
    for key, value in inherited.items():
        monkeypatch.setenv(key, value)
    original = (storage.STORE, evidence.STORE, access._RATE_LIMITER,
                formparsers.SpooledTemporaryFile)
    prior_stores = []
    for _ in range(2):
        with upload_state_factory() as fresh:
            assert new_records(fresh) == ([], [])
            assert all(fresh['store'] is not prior for prior in prior_stores)
            assert fresh['store'] is not original[0]
            assert access._RATE_LIMITER is not original[2]
            response, _ = request(fresh, multipart_body())
            assert_success(response, fresh, data=b'Synthetic upload only.\n')
            prior_stores.append(fresh['store'])
        assert all(handle.closed for handle in fresh['files'])
        restored = (storage.STORE, evidence.STORE, access._RATE_LIMITER,
                    formparsers.SpooledTemporaryFile)
        assert all(before is after for before, after in zip(original, restored))
        assert {key: os.environ[key] for key in inherited} == inherited
