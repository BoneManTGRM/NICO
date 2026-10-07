"""Prepare private retained diagnostic inputs using normal read-only Actions transport.

Source identities below bind reviewed public code. Original image/baseline
selection and receipts remain in host scratch. The explicit capacity mode pins
only its separately retained a583 input run/artifact and whole-byte identities.
This program does not load an image, create a container, or execute an analyzer.
"""
from __future__ import annotations

import importlib.machinery, importlib.util

import argparse
import ast
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import time
import types
import urllib.error
import urllib.parse
import urllib.request
import zipfile

sys.dont_write_bytecode = True
API = 'https://api.github.com'
REPOSITORY = 'BoneManTGRM/NICO'
IMAGE_BRANCH = 'diagnostic/v17-pinned-image-20261007'
BASELINE_BRANCH = 'repair/v15-fileapi-evidence-20261005'
IMAGE_WORKFLOW = '.github/workflows/cpp-diagnostic-image-rebuild.yml'
BASELINE_WORKFLOW = '.github/workflows/cpp-full-project-integration.yml'
MAX_META = 8 * 1024 * 1024
MAX_MEMBER = 64 * 1024 * 1024
MAX_ARCHIVE = 3 * 1024 * 1024 * 1024
# New conservative transport guard, not a recovered historical host limit.
MAX_SCRATCH = 6 * 1024 * 1024 * 1024
MAX_PAGES = 1
MAX_REDIRECTS = 2
REQUEST_SECONDS = 30
SOURCE_PINS = {
    'scripts/cpp_private_parser_worker.py':
        '9a12d14dd5ab388bc1f007b54acb343f755870c2ffc338ca2f617a0d8422e3b8',
    'scripts/cpp_same_image_dependency_diagnostic.py':
        'daad27799550a82955bdc69a3b067ce0722fb8669e25527d40298173b0bac417',
    'scripts/cpp_diagnostic_image_rebuild.py':
        '079e02d0d71bef281e760067a25e614b70be37bbf479705ee6e84ebf45dc8344',
    'scripts/cpp_diagnostic_image_inputs.json':
        '5e77eb4b1a01d2d29829ba2b34de56f599d917f6bdf3d1c41ff43469d8abc290',
    IMAGE_WORKFLOW: 'd72da3ffc5f3f39ef6bb8b12cb000fd5e888a65adf512c049ca2566622be30ac',
    'nico/assessment_cpp_project_compiler.py':
        '89b2cf72c00bdbde55fcdb42efeeaaeb11ad28ddae4e16cd99c59f6d3e5316e8',
    'scripts/cpp-parser-diagnostic-inputs/baseline_compiler.py':
        'be5b8be8386189af7f51e2ce47681b181a6c71a5e8384146da6deb8289e81276',
    'scripts/cpp-parser-diagnostic-inputs/source_path_evidence.py':
        'bc26c3bb86c0673793c118f969234ece3bc4939325af3703b2da69259eb4a242',
    'scripts/cpp-parser-diagnostic-inputs/owned_fixture_harness.py':
        '33a24638af025747aec04bac3b7bb5738a64e7eaa8cfa0ff04ef7f5d2192b1cb',
}
FUNCTION_PINS = {
    'baseline': 'ac98c8befe38d88c3bfcdfa42ae3a431629eb6cda736f4630702eab5b03bfc89',
    'candidate': '8f131a5839f4659b447bc6ba6e4f236e153e990ea363f2208ae151e5e8ee66de',
    'source_path': 'ea169cef57a04a6d2767c45e53242227b3316d011845c66916590fd14bbf6847',
    'fixtures': '713b754d533645426fe525652775392f66d0dcb265980bc9b5468a1275c78c10',
}
DECODER_FUNCTION_PINS = {
    'inputs': '9f87a76418756526d5a1561ef852f186634db8cb945b9975d215d9e42040e9ae',
    'regular': '45bf871234eb23665c031c2780f460fe1fbb3e5b2eab33c3f49c2153a12068ae',
}



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

class PreparationError(ValueError):
    """Only fixed safe codes, never provider errors, URLs or credentials."""


def require(ok, code):
    if not ok:
        raise PreparationError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def unique(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate_json_key')
        result[key] = value
    return result


def decode(raw):
    try:
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: require(False, 'nonfinite_json'))
    except PreparationError:
        raise
    except (ValueError, UnicodeError):
        raise PreparationError('invalid_json') from None


def safe_name(name):
    require(isinstance(name, str) and 0 < len(name) <= 240
            and PurePosixPath(name).as_posix() == name and not name.startswith('/')
            and re.fullmatch(r'[A-Za-z0-9._/-]+', name) is not None
            and all(part not in {'', '.', '..'} for part in name.split('/')), 'unsafe_member_path')
    return name


def write_private(path, value):
    raw = canonical(value) + b'\n'
    require(len(raw) <= MAX_META, 'private_metadata_bound')
    with path.open('xb') as stream:
        os.chmod(path, 0o600)
        stream.write(raw)


def safe_transport_url(url, api=False):
    try:
        part = urllib.parse.urlsplit(url)
        port = part.port
    except (ValueError, TypeError):
        raise PreparationError('transport_url') from None
    host = part.hostname or ''
    require(part.scheme == 'https' and part.username is None and part.password is None
            and port in (None, 443) and not part.fragment, 'transport_url')
    if api:
        require(host == 'api.github.com' and not part.query and
                re.fullmatch(r'/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/actions/artifacts/[0-9]+/zip',
                             part.path) is not None, 'artifact_api_url')
    else:
        # Official Actions essential-communications authority: *.blob.core.windows.net.
        # A literal suffix separator is required; lookalike suffixes are rejected.
        require(host.endswith('.blob.core.windows.net') and
                re.fullmatch(r'[a-z0-9-]+\.blob\.core\.windows\.net', host) is not None,
                'artifact_transport_host')
    return url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ActionsClient:
    """GET only; token stays on the API origin, including through redirects."""
    def __init__(self, token):
        require(isinstance(token, str) and token and '\r' not in token and '\n' not in token,
                'job_token_required')
        self._token = token
        self._opener = urllib.request.build_opener(NoRedirect())

    def _get(self, url, authenticated):
        headers = {'User-Agent': 'nico-private-diagnostic-preparation'}
        if authenticated:
            require(urllib.parse.urlsplit(url).netloc == 'api.github.com', 'credential_origin')
            headers.update(Authorization='Bearer ' + self._token,
                           Accept='application/vnd.github+json', **{'X-GitHub-Api-Version': '2022-11-28'})
        request = urllib.request.Request(url, headers=headers, method='GET')
        try:
            return self._opener.open(request, timeout=REQUEST_SECONDS)
        except urllib.error.HTTPError as error:
            if error.code in (301, 302, 303, 307, 308):
                return error
            error.close()
            raise PreparationError('provider_read_failed') from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise PreparationError('transport_failed') from None

    def json(self, path):
        # Paths are constructed locally; no provider-supplied URL is followed here.
        require(path.startswith('/repos/') and not any(c in path for c in ['\r', '\n', '#'])
                and urllib.parse.urlsplit(path).netloc == '', 'api_path')
        with self._get(API + path, True) as response:
            require(response.code == 200, 'api_redirect_or_status')
            raw = response.read(MAX_META + 1)
        require(len(raw) <= MAX_META, 'api_response_bound')
        return decode(raw)

    def download(self, artifact, destination, maximum):
        url = safe_transport_url(artifact['archive_download_url'], api=True)
        expected = artifact_digest(artifact, maximum)
        response = None
        for number in range(MAX_REDIRECTS + 1):
            response = self._get(url, number == 0)
            if response.code == 200:
                break
            require(response.code in (301, 302, 303, 307, 308) and number < MAX_REDIRECTS,
                    'artifact_redirect_limit')
            location = response.headers.get('Location')
            response.close()
            url = safe_transport_url(urllib.parse.urljoin(url, location or ''))
        require(response is not None and response.code == 200, 'artifact_status')
        digest = hashlib.sha256()
        total = 0
        started = time.perf_counter_ns()
        try:
            with response, destination.open('xb') as stream:
                os.chmod(destination, 0o600)
                length = response.headers.get('Content-Length')
                require(length is None or (length.isdecimal() and int(length) == artifact['size_in_bytes']),
                        'artifact_content_length')
                while body := response.read(1024 * 1024):
                    total += len(body)
                    require(total <= maximum and total <= artifact['size_in_bytes'], 'artifact_stream_size')
                    digest.update(body)
                    stream.write(body)
            require(total == artifact['size_in_bytes'] and digest.hexdigest() == expected,
                    'provider_zip_digest_or_size')
        except PreparationError:
            raise
        except (OSError, urllib.error.URLError, TimeoutError):
            raise PreparationError('artifact_stream_failed') from None
        return {'bytes': total, 'sha256': digest.hexdigest(),
                'wall_ms': (time.perf_counter_ns() - started) / 1e6,
                'provider_raw_zip_verified': True}


def artifact_digest(row, maximum):
    require(type(row.get('id')) is int and row['id'] > 0 and row.get('expired') is False
            and type(row.get('size_in_bytes')) is int and 0 < row['size_in_bytes'] <= maximum
            and isinstance(row.get('digest'), str)
            and re.fullmatch(r'sha256:[0-9a-f]{64}', row['digest']) is not None, 'artifact_metadata')
    try:
        expiry = dt.datetime.fromisoformat(row['expires_at'].replace('Z', '+00:00'))
    except (KeyError, AttributeError, ValueError):
        raise PreparationError('artifact_expiry') from None
    require(expiry.tzinfo is not None and expiry > dt.datetime.now(dt.timezone.utc), 'artifact_expired')
    return row['digest'][7:]


def bounded_catalog(value, key):
    require(isinstance(value, dict) and type(value.get('total_count')) is int
            and 0 <= value['total_count'] <= 100 and isinstance(value.get(key), list)
            and len(value[key]) == value['total_count'], 'bounded_catalog_incomplete')
    return value[key]


def one(rows, code):
    require(len(rows) == 1, code)
    return rows[0]


def run_identity(run, workflow, branch, event, conclusion, repository_id, head=None):
    return (type(run.get('id')) is int and run['id'] > 0 and run.get('path') == workflow
            and run.get('head_branch') == branch and run.get('event') == event
            and run.get('status') == 'completed' and run.get('conclusion') == conclusion
            and run.get('run_attempt') == 1 and run.get('repository', {}).get('id') == repository_id
            and run.get('head_repository', {}).get('id') == repository_id
            and re.fullmatch(r'[0-9a-f]{40}', str(run.get('head_sha', ''))) is not None
            and (head is None or run['head_sha'] == head))


def source_tree(client, repository, commit):
    require(re.fullmatch(r'[0-9a-f]{40}', commit) is not None, 'source_commit_format')
    value = client.json('/repos/' + repository + '/git/commits/' + commit)
    require(value.get('sha') == commit, 'remote_source_commit')
    tree = value['tree']['sha']
    require(re.fullmatch(r'[0-9a-f]{40}', tree) is not None, 'remote_tree_format')
    inventory = client.json('/repos/' + repository + '/git/trees/' + tree + '?recursive=1')
    require(inventory.get('sha') == tree and inventory.get('truncated') is False
            and isinstance(inventory.get('tree'), list), 'remote_source_tree')
    rows = {}
    for row in inventory['tree']:
        require(isinstance(row.get('path'), str) and row['path'] not in rows, 'remote_duplicate_path')
        rows[row['path']] = row
    return value, rows


def select_run(client, workflow, branch, event, conclusion, repository_id, head=None, blobs=None):
    query = urllib.parse.urlencode({'branch': branch, 'event': event, 'per_page': 100})
    path = '/repos/' + REPOSITORY + '/actions/workflows/' + workflow.rsplit('/', 1)[-1] + '/runs?' + query
    rows = bounded_catalog(client.json(path), 'workflow_runs')
    matched = []
    for row in rows:
        if not run_identity(row, workflow, branch, event, conclusion, repository_id, head):
            continue
        if blobs is not None:
            commit, tree = source_tree(client, REPOSITORY, row['head_sha'])
            if any(tree.get(name, {}).get('sha') != wanted or tree[name].get('mode') != '100644'
                   or tree[name].get('type') != 'blob' for name, wanted in blobs.items()):
                continue
            row = dict(row, verified_tree=commit['tree']['sha'])
        matched.append(row)
    result = one(matched, 'run_missing_or_ambiguous')
    attempt = client.json('/repos/' + REPOSITORY + '/actions/runs/' + str(result['id']) + '/attempts/1')
    require(run_identity(attempt, workflow, branch, event, conclusion, repository_id, result['head_sha'])
            and attempt['id'] == result['id'], 'run_attempt_binding')
    return result


def select_artifact(client, run, name, repository_id, maximum):
    rows = bounded_catalog(client.json('/repos/' + REPOSITORY + '/actions/runs/' +
                                      str(run['id']) + '/artifacts?per_page=100'), 'artifacts')
    result = one([row for row in rows if row.get('name') == name], 'artifact_missing_or_ambiguous')
    binding = result.get('workflow_run', {})
    require(binding.get('id') == run['id'] and binding.get('head_sha') == run['head_sha']
            and binding.get('head_branch') == run['head_branch']
            and binding.get('repository_id') == binding.get('head_repository_id') == repository_id,
            'artifact_run_binding')
    artifact_digest(result, maximum)
    require(result.get('archive_download_url') == API + '/repos/' + REPOSITORY +
            '/actions/artifacts/' + str(result['id']) + '/zip', 'artifact_locator_binding')
    return result


def scratch_bytes(root):
    total = 0
    for directory, directories, files in os.walk(root, followlinks=False):
        require(all(not (Path(directory) / name).is_symlink() for name in directories), 'scratch_symlink')
        for name in files:
            value = (Path(directory) / name).lstat()
            require(stat.S_ISREG(value.st_mode), 'scratch_special_file')
            total += value.st_size
    return total


def preflight(root, additional, load_store_reserve):
    current = scratch_bytes(root)
    require(type(additional) is int and additional >= 0 and current + additional <= MAX_SCRATCH,
            'transient_scratch_guard')
    require(type(load_store_reserve) is int and load_store_reserve > 0, 'load_store_reserve_required')
    free = shutil.disk_usage(root).free
    require(free >= additional + load_store_reserve, 'host_free_disk_guard')
    return {'existing_bytes': current, 'additional_bound_bytes': additional,
            'peak_bound_bytes': current + additional, 'free_disk_bytes': free,
            'separately_supplied_load_store_reserve_bytes': load_store_reserve,
            'load_store_actual_cost_known': False, 'transient_guard_bytes': MAX_SCRATCH,
            'guard_is_new_conservative_implementation_limit': True,
            'historical_host_limit_recovered': False, 'container_tmpfs_used_as_host_allowance': False}


def extract_verified_zip(path, output, count, maximum_member, maximum_total, expected_names=None,
                         member_limits=None):
    """Called only after whole provider ZIP SHA/length verification; checks every CRC."""
    output.mkdir(mode=0o700)
    rows = []
    names = set()
    total = 0
    try:
        with zipfile.ZipFile(path) as bundle:
            members = bundle.infolist()
            require(len(members) <= count + 64, 'zip_entry_count')
            files = []
            for row in members:
                name = safe_name(row.filename.rstrip('/') if row.is_dir() else row.filename)
                require(name not in names and not row.flag_bits & 1, 'zip_duplicate_or_encrypted')
                names.add(name)
                mode = row.external_attr >> 16
                kind = stat.S_IFMT(mode)
                require(kind in (0, stat.S_IFDIR if row.is_dir() else stat.S_IFREG), 'zip_special_member')
                if row.is_dir():
                    require(row.file_size == 0, 'zip_directory_size')
                    continue
                limit = maximum_member if member_limits is None else member_limits.get(name, maximum_member)
                require(0 <= row.file_size <= limit, 'decoded_member_size')
                total += row.file_size
                require(total <= maximum_total, 'decoded_total_size')
                files.append((row, name))
            require(len(files) == count and (expected_names is None or
                    {name for row, name in files} == set(expected_names)), 'decoded_member_population')
            for row, name in files:
                destination = output / name
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                digest = hashlib.sha256()
                used = 0
                with bundle.open(row) as source, destination.open('xb') as sink:
                    os.chmod(destination, 0o600)
                    while body := source.read(1024 * 1024):
                        used += len(body)
                        require(used <= row.file_size and used <= maximum_member, 'decoded_stream_size')
                        digest.update(body)
                        sink.write(body)
                require(used == row.file_size, 'decoded_stream_length')
                rows.append({'path': name, 'bytes': used, 'sha256': digest.hexdigest()})
    except PreparationError:
        raise
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, EOFError):
        raise PreparationError('zip_decode_failed') from None
    return sorted(rows, key=lambda row: row['path'])


def ast_digest(raw, name):
    tree = ast.parse(raw)
    rows = [row for row in tree.body if isinstance(row, ast.FunctionDef) and row.name == name]
    require(len(rows) == 1, 'function_population')
    # CPython3.12 added an empty field to these definitions. Canonicalize only
    # that absence/empty-list distinction; meaningful parameters are rejected.
    # Whole-file source hashes remain independently required before this helper.
    for row in ast.walk(rows[0]):
        if isinstance(row, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            parameters = getattr(row, 'type_params', [])
            require(type(parameters) is list and not parameters, 'unsupported_ast_type_parameters')
            if 'type_params' in row._fields:
                row._fields = tuple(field for field in row._fields if field != 'type_params')
    return sha(ast.dump(rows[0], include_attributes=False).encode())


def verified_source_bodies(operation):
    bodies = {}
    for name, expected in SOURCE_PINS.items():
        path = operation / name
        require(path.resolve(strict=True) == path and not path.is_symlink(), 'source_path')
        raw = path.read_bytes()
        require(len(raw) <= MAX_MEMBER and sha(raw) == expected, 'reviewed_public_source_digest')
        bodies[name] = raw
    return bodies


def supported_operation_identity(environment, head):
    # Closed route pairs. A new diagnostic route never impersonates the old job.
    routes = {
        'same-image-parser-diagnostic': '.github/workflows/cpp-same-image-parser-diagnostic.yml',
        'same-image-full-static-diagnostic': '.github/workflows/cpp-same-image-full-static-diagnostic.yml',
    }
    workflow = routes.get(environment.get('GITHUB_JOB'))
    return bool(workflow is not None and environment.get('GITHUB_REPOSITORY') == REPOSITORY
        and environment.get('GITHUB_REF') == 'refs/heads/' + IMAGE_BRANCH
        and environment.get('GITHUB_EVENT_NAME') == 'push'
        and environment.get('GITHUB_RUN_ATTEMPT') == '1'
        and environment.get('RUNNER_ENVIRONMENT') == 'github-hosted'
        and environment.get('GITHUB_WORKFLOW_SHA') == head
        and environment.get('GITHUB_WORKFLOW_REF') == REPOSITORY + '/' + workflow + '@refs/heads/' + IMAGE_BRANCH
        and re.fullmatch(r'[0-9a-f]{40}', head or '') is not None)


def checked_sources(operation, recipe):
    bodies = verified_source_bodies(operation)
    helper = _import_verified_buffer(operation / 'scripts/cpp_diagnostic_image_rebuild.py',
        bodies['scripts/cpp_diagnostic_image_rebuild.py'], 'hash_bound_image_archive_helper')
    inputs = decode(bodies['scripts/cpp_diagnostic_image_inputs.json'])
    checked = helper.checked_git_source(recipe, inputs['recipe_source_sha'], inputs['recipe_source_tree'], 3305)
    head = os.environ.get('GITHUB_SHA', '')
    require(supported_operation_identity(os.environ, head), 'operation_authority_identity')
    operation_proof = helper.checked_git_source(operation, head)
    sources = {}
    mapping = {'baseline': ('scripts/cpp-parser-diagnostic-inputs/baseline_compiler.py',
                             'nico/assessment_cpp_project_compiler.py'),
               'source_path': ('scripts/cpp-parser-diagnostic-inputs/source_path_evidence.py',
                                'nico/assessment_cpp_compiler_evidence.py'),
               'candidate': ('nico/assessment_cpp_project_compiler.py', None),
               'fixtures': ('scripts/cpp-parser-diagnostic-inputs/owned_fixture_harness.py', None)}
    for key, (name, original) in mapping.items():
        raw = bodies[name]
        if original:
            require(helper.regular(recipe / original, MAX_MEMBER) == raw, 'original_recipe_source_copy')
        function = 'fixtures' if key == 'fixtures' else ('_source_path' if key == 'source_path'
                                                       else '_dependency_populations')
        require(ast_digest(raw, function) == FUNCTION_PINS[key], 'reviewed_function_ast')
        sources[key] = {'path': name, 'bytes': len(raw), 'sha256': sha(raw), 'git_blob': blob(raw)}
        if original:
            sources[key]['original_recipe_path'] = original
    program = operation / 'scripts/cpp_same_image_dependency_diagnostic.py'
    # Execute the exact byte buffer already verified above, not a later re-read.
    program_raw = bodies['scripts/cpp_same_image_dependency_diagnostic.py']
    for name, expected in DECODER_FUNCTION_PINS.items():
        require(ast_digest(program_raw, name) == expected, 'unchanged_retained_decoder_ast')
    worker = _import_verified_buffer(program, program_raw, 'actual_reviewed_retained_input_decoder')
    return helper, worker, inputs, checked, operation_proof, sources, program_raw


def verify_receipt_identity(receipt, run, recipe, status, helper_sha):
    operation = receipt.get('operation', {})
    source = receipt.get('recipe_source', {})
    require(receipt.get('status') == status and receipt.get('production_qualified') is False
            and receipt.get('historical_image_recovered') is False and receipt.get('target_execution') is False
            and operation.get('workflow_head') == run['head_sha']
            and operation.get('workflow_tree') == run['verified_tree']
            and operation.get('run_id') == str(run['id']) and operation.get('run_attempt') == 1
            and operation.get('helper_sha256') == helper_sha
            and source.get('commit') == recipe['commit'] and source.get('tree') == recipe['tree']
            and source.get('tracked_files') == 3305
            and source.get('tracked_byte_blob_mode_inventory_sha256') ==
                recipe['tracked_byte_blob_mode_inventory_sha256'], 'image_receipt_identity')
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', str(receipt.get('image_config_id', ''))) is not None
            and receipt['image_inspection']['Id'] == receipt['image_config_id']
            and receipt['image_inspection']['Architecture'] == 'amd64'
            and receipt['image_inspection']['Os'] == 'linux', 'image_config_identity')


def exact_inventory_paths(inventory, rows):
    paths = [row['path'] for row in inventory]
    require(len(paths) == len(set(paths)) and set(paths) == set(rows),
            'frozen_target_exact_unique_path_population')


def retained_copy(raw, ref):
    require(len(raw) == ref['bytes'] and sha(raw) == ref['sha256'], 'runtime_retained_copy_binding')
    return raw


def runtime_write(root, name, raw):
    """Only an explicitly minimized tree is readable by container user1000."""
    destination = root / name
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    for parent in destination.parents:
        os.chmod(parent, 0o755)
        if parent == root:
            break
    destination.write_bytes(raw)
    os.chmod(destination, 0o644)
    return destination


def prepare(client, operation, recipe, scratch, load_store_reserve):
    require(not scratch.exists() and scratch.parent.resolve(strict=True) == scratch.parent,
            'new_canonical_scratch')
    scratch.mkdir(mode=0o700)
    host = scratch / 'host'
    host.mkdir(mode=0o700)
    helper, worker, recipe_inputs, recipe_proof, operation_proof, sources, program_raw = checked_sources(operation, recipe)
    repo = client.json('/repos/' + REPOSITORY)
    require(repo.get('full_name') == REPOSITORY and repo.get('private') is False
            and str(repo.get('id')) == os.environ.get('GITHUB_REPOSITORY_ID'), 'repository_binding')
    repository_id = repo['id']
    recipe_commit, recipe_tree = source_tree(client, REPOSITORY, recipe_proof['commit'])
    require(recipe_commit['tree']['sha'] == recipe_proof['tree']
            and [row['sha'] for row in recipe_commit['parents']] == [recipe_inputs['recipe_parent_sha']],
            'remote_recipe_tree_and_actual_parent')
    producer_commit, producer_tree = source_tree(client, REPOSITORY, recipe_inputs['recipe_original_producer'])
    parent_commit, parent_tree = source_tree(client, REPOSITORY, recipe_inputs['recipe_parent_sha'])
    require(producer_commit['tree']['sha'] == parent_commit['tree']['sha']
            and recipe_inputs['recipe_parent_sha'] in [row['sha'] for row in producer_commit['parents']],
            'legitimate_baseline_test_merge_source')
    for row in recipe_inputs['trusted_recipe_files']:
        require(recipe_tree.get(row['path'], {}).get('sha') == row['git_blob']
                and producer_tree.get(row['path'], {}).get('sha') == row['git_blob'], 'producer_recipe_file_binding')
    image_blobs = {name: blob(helper.regular(operation / name, MAX_MEMBER))
                   for name in ('scripts/cpp_diagnostic_image_rebuild.py',
                                'scripts/cpp_diagnostic_image_inputs.json', IMAGE_WORKFLOW)}
    image_run = select_run(client, IMAGE_WORKFLOW, IMAGE_BRANCH, 'push', 'success', repository_id,
                           blobs=image_blobs)
    baseline_run = select_run(client, BASELINE_WORKFLOW, BASELINE_BRANCH, 'pull_request', 'failure',
                              repository_id, head=recipe_inputs['recipe_parent_sha'])
    suffix = image_run['head_sha'] + '-' + str(image_run['id']) + '-1'
    image_artifact = select_artifact(client, image_run, 'diagnostic-image-' + suffix, repository_id, MAX_ARCHIVE)
    retrieval_artifact = select_artifact(client, image_run, 'diagnostic-image-retrieval-' + suffix,
                                        repository_id, MAX_META)
    baseline_artifact = select_artifact(client, baseline_run, 'cpp-baseline-qualification-' +
                                       recipe_inputs['recipe_original_producer'] + '-' +
                                       str(baseline_run['id']) + '-1', repository_id, MAX_MEMBER)
    records = {'schema': 'nico.private.runtime_preparation.v1', 'status': 'UNPROVEN',
               'source': operation_proof, 'recipe_source': recipe_proof, 'image_run': image_run,
               'baseline_run': baseline_run, 'provider_records': {'image': image_artifact,
                    'retrieval': retrieval_artifact, 'baseline': baseline_artifact},
               'preflights': [], 'downloads': {}, 'actual_observed_scratch_peak_bytes': 0,
               'required_full_obligations_unchanged':
                   {'contexts': 577, 'fallback_contexts': 576, 'full_headers_and_generated_inputs': True},
               'target_or_native_execution': False, 'new_image_build': False,
               'public_metadata_export': False, 'new_artifact_upload': False}
    records['preflights'].append(preflight(scratch, retrieval_artifact['size_in_bytes'] + MAX_META,
                                          load_store_reserve))
    zip_path = host / 'retrieval.zip'
    records['downloads']['retrieval'] = client.download(retrieval_artifact, zip_path, MAX_META)
    extract_verified_zip(zip_path, host / 'retrieval', 1, MAX_META, MAX_META, {'receipt.json'})
    records['actual_observed_scratch_peak_bytes'] = max(records['actual_observed_scratch_peak_bytes'], scratch_bytes(scratch))
    zip_path.unlink()
    retrieval_raw = helper.regular(host / 'retrieval/receipt.json', MAX_META)
    retrieval = decode(retrieval_raw)
    verify_receipt_identity(retrieval, image_run, recipe_proof,
                            'DIAGNOSTIC_IMAGE_RETRIEVED_COMPLETE_IDENTITY_VERIFIED',
                            SOURCE_PINS['scripts/cpp_diagnostic_image_rebuild.py'])
    require(retrieval.get('supported_storage_retrieval_verified') is True
            and retrieval.get('complete_image_archive_verified') is True
            and retrieval.get('new_runner_image_absent_before_load') is True
            and re.fullmatch(r'[0-9a-f]{64}', str(retrieval.get('build_receipt_sha256', ''))) is not None,
            'independent_fresh_retrieval_anchor')
    tar_size = retrieval['archive_proof']['archive']['bytes']
    require(type(tar_size) is int and 0 < tar_size <= MAX_ARCHIVE, 'retained_tar_size')
    records['preflights'].append(preflight(scratch, baseline_artifact['size_in_bytes'] + 32 * MAX_MEMBER,
                                          load_store_reserve))
    zip_path = host / 'baseline.zip'
    records['downloads']['baseline'] = client.download(baseline_artifact, zip_path, MAX_MEMBER)
    members = extract_verified_zip(zip_path, host / 'baseline', 32, MAX_MEMBER, 32 * MAX_MEMBER)
    records['actual_observed_scratch_peak_bytes'] = max(records['actual_observed_scratch_peak_bytes'], scratch_bytes(scratch))
    zip_path.unlink()
    receipt_raw = helper.regular(host / 'baseline/cpp-baseline-qualification/receipt.json', MAX_MEMBER)
    receipt = decode(receipt_raw)
    probe = receipt['probe']
    benchmark = helper.regular(recipe / 'tests/fixtures/cpp/bitcoin-configuration-benchmark.json', MAX_META)
    fixture = decode(benchmark)
    require(receipt['benchmark_sha256'] == sha(benchmark)
            and receipt['producer_source_sha'] == recipe_inputs['recipe_original_producer'], 'baseline_recipe_binding')
    source = receipt['source']
    frozen_commit, frozen_rows = source_tree(client, fixture['repository'], fixture['commit_sha'])
    require(frozen_commit['tree']['sha'] == fixture['tree_sha'] == source['tree_sha']
            and source['commit_sha'] == fixture['commit_sha'] and source['repository'] == fixture['repository']
            and len(source['inventory']) == len(frozen_rows) == 3248
            and source['materialized_files'] == 3031, 'frozen_target_git_population')
    exact_inventory_paths(source['inventory'], frozen_rows)
    for row in source['inventory']:
        actual = frozen_rows.get(row['path'], {})
        require(actual.get('sha') == row['git_blob'] and actual.get('type') == row['git_type']
                and actual.get('mode') == row['git_mode'], 'frozen_target_git_blob_mode')
    baseline = {'members': members, 'receipt_sha256': sha(receipt_raw),
                'producer_source': receipt['producer_source_sha'],
                'historical_image_id': probe['image_config_digest'],
                'compiler': probe['project_compiler']['artifact'],
                'snapshot': probe['generated_context']['artifact'],
                'snapshot_population_sha256': decode(helper.regular(host / 'baseline/cpp-baseline-qualification' /
                    safe_name(probe['generated_context']['artifact']['path']), MAX_MEMBER))['file_population_sha256']}
    frozen = {'repository': fixture['repository'], 'commit': fixture['commit_sha'], 'tree': fixture['tree_sha'],
              'target_population_sha256': probe['source_population_sha256']}
    host_pins = {'schema': 'nico.c34.same_image_parser_diagnostic_input_pins.v1',
                 'recipe_source': {'commit': recipe_proof['commit'], 'tree': recipe_proof['tree'], 'tracked_files': 3305},
                 'sources': sources, 'functions': dict(FUNCTION_PINS), 'frozen_target': frozen,
                 'diagnostic_script_sha256': sha(program_raw), 'baseline': baseline,
                 'image': {'image_config_id': retrieval['image_config_id'], 'tar_bytes': tar_size,
                    'tar_sha256': retrieval['archive_proof']['archive']['sha256'],
                    'expected_layers': retrieval['image_inspection']['RootFS']['Layers'],
                    'build_receipt_sha256': retrieval['build_receipt_sha256'],
                    'prior_retrieval_receipt_sha256': sha(retrieval_raw),
                    'build_head': image_run['head_sha'], 'build_tree': image_run['verified_tree'],
                    'run_id': image_run['id'], 'run_attempt': 1}}
    # Original decoder, unchanged AST, verifies every actual input before minimization.
    request, dependencies, retained, provenance = worker.inputs(host / 'baseline', host_pins)
    records['retained_decoder_provenance'] = provenance
    runtime = scratch / 'runtime'
    runtime.mkdir(mode=0o755)
    os.chmod(runtime, 0o755)
    runtime_inputs = runtime / 'inputs'
    runtime_inputs.mkdir(mode=0o755)
    os.chmod(runtime_inputs, 0o755)
    for key in ('compiler', 'snapshot'):
        ref = baseline[key]
        raw = helper.regular(host / 'baseline/cpp-baseline-qualification' / safe_name(ref['path']), MAX_MEMBER)
        retained_copy(raw, ref)
        (runtime_inputs / (key + '.json')).write_bytes(raw)
        os.chmod(runtime_inputs / (key + '.json'), 0o644)
    input_manifest = {'schema': 'nico.runtime.retained_parser_inputs.v1', 'targets': request['targets'],
                      'generated_files': request['generated_files'],
                      'target_population_sha256': frozen['target_population_sha256'],
                      'snapshot_population_sha256': baseline['snapshot_population_sha256']}
    manifest_raw = canonical(input_manifest) + b'\n'
    require(len(manifest_raw) <= MAX_META, 'runtime_manifest_bound')
    (runtime_inputs / 'input-manifest.json').write_bytes(manifest_raw)
    os.chmod(runtime_inputs / 'input-manifest.json', 0o644)
    runtime_members = [{'path': name, 'bytes': (runtime_inputs / name).stat().st_size,
                        'sha256': sha((runtime_inputs / name).read_bytes())}
                       for name in ('compiler.json', 'snapshot.json', 'input-manifest.json')]
    runtime_source = runtime / 'source'
    runtime_source.mkdir(mode=0o755)
    os.chmod(runtime_source, 0o755)
    for row in sources.values():
        destination = runtime_source / row['path']
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        for parent in destination.parents:
            if parent == runtime_source:
                break
            os.chmod(parent, 0o755)
        copied = helper.regular(operation / row['path'], MAX_MEMBER)
        require(len(copied) == row['bytes'] and sha(copied) == row['sha256'], 'runtime_source_copy_binding')
        destination.write_bytes(copied)
        os.chmod(destination, 0o644)
    program_path = runtime_source / 'scripts/cpp_same_image_dependency_diagnostic.py'
    program_path.write_bytes(program_raw)
    os.chmod(program_path, 0o644)
    wrapper_raw = helper.regular(operation / 'scripts/cpp_private_parser_worker.py', MAX_MEMBER)
    require(sha(wrapper_raw) == SOURCE_PINS['scripts/cpp_private_parser_worker.py'], 'runtime_wrapper_source_binding')
    runtime_write(runtime_source, 'scripts/cpp_private_parser_worker.py', wrapper_raw)
    runtime_pins = {'schema': 'nico.runtime.same_image_parser_pins.v1', 'sources': sources,
                    'functions': dict(FUNCTION_PINS), 'diagnostic_script_sha256': sha(program_raw),
                    'image': {'image_config_id': host_pins['image']['image_config_id'],
                              'tar_sha256': host_pins['image']['tar_sha256']},
                    'runtime_members': runtime_members, 'frozen_target': frozen}
    runtime_pin_path = runtime_source / 'scripts/cpp-parser-diagnostic-inputs/runtime-pins.json'
    runtime_pin_path.write_bytes(canonical(runtime_pins) + b'\n')
    os.chmod(runtime_pin_path, 0o644)
    records['preflights'].append(preflight(scratch, image_artifact['size_in_bytes'] + tar_size + 2 * MAX_META,
                                          load_store_reserve))
    zip_path = host / 'image.zip'
    records['downloads']['image'] = client.download(image_artifact, zip_path, MAX_ARCHIVE)
    image_members = extract_verified_zip(zip_path, host / 'image', 3, MAX_ARCHIVE,
                                         tar_size + 2 * MAX_META, {'receipt.json', 'build.log', 'image.tar'},
                                         {'receipt.json': MAX_META, 'build.log': MAX_META, 'image.tar': tar_size})
    records['actual_observed_scratch_peak_bytes'] = max(records['actual_observed_scratch_peak_bytes'], scratch_bytes(scratch))
    zip_path.unlink()
    image_members_by_name = {row['path']: row for row in image_members}
    require(image_members_by_name['receipt.json']['bytes'] <= MAX_META
            and image_members_by_name['build.log']['bytes'] <= MAX_META
            and image_members_by_name['image.tar']['bytes'] == tar_size
            and image_members_by_name['image.tar']['sha256'] == host_pins['image']['tar_sha256'],
            'image_decoded_member_bounds')
    build_raw = helper.regular(host / 'image/receipt.json', MAX_META)
    require(sha(build_raw) == retrieval['build_receipt_sha256'], 'independent_build_receipt_anchor')
    build = decode(build_raw)
    verify_receipt_identity(build, image_run, recipe_proof, 'DIAGNOSTIC_IMAGE_SAVED_UNRETRIEVED',
                            SOURCE_PINS['scripts/cpp_diagnostic_image_rebuild.py'])
    require(build['image_config_id'] == retrieval['image_config_id']
            and build['image_inspection']['RootFS']['Layers'] == retrieval['image_inspection']['RootFS']['Layers']
            and build['image_inspection']['Config'] == retrieval['image_inspection']['Config']
            and build['archive_proof'] == retrieval['archive_proof'], 'independent_complete_image_receipts')
    proof = helper.archive_proof(host / 'image/image.tar', build['image_config_id'],
                                 build['image_inspection']['RootFS']['Layers'])
    require(proof == build['archive_proof'], 'actual_every_layer_archive_proof')
    records.update(status='PRIVATE_RETAINED_INPUTS_PREPARED', complete_archive_proof=proof,
                   actual_scratch_bytes_before_final_host_records=scratch_bytes(scratch),
                   runtime_pin_sha256=sha(runtime_pin_path.read_bytes()),
                   adapter_sha256=sha(Path(__file__).read_bytes()),
                   decoded_provider_raw_zip_not_old_local_annotation=True,
                   historical_exact_image_replay_satisfied=False,
                   image_load_store_actual_bytes=None,
                   load_store_reserve_is_preflight_allowance_not_a_measurement=True)
    write_private(host / 'pins.json', host_pins)
    write_private(host / 'preparation.json', records)
    return records


CAPACITY_INPUT_RUN = 37659207160
CAPACITY_INPUT_HEAD = 'a5835f2dbb2b671443356de2d0808bdbc731dd6d'
CAPACITY_INPUT_WORKFLOW = '.github/workflows/cpp-same-image-full-static-diagnostic.yml'
CAPACITY_INPUT_ARTIFACT = {
    'id': 11501588664,
    'name': 'cpp-full-static-candidate-a5835f2dbb2b671443356de2d0808bdbc731dd6d-37659207160-1',
    'bytes': 12525552,
    'sha256': '787121b582ec1709cadaa775345914e4e1a1543ef48810cf775818590b6cd011',
}
CAPACITY_INPUT_MEMBERS = {
    'environment': {'path': 'artifacts/project-static-environment-39c5e0dc127ae3d7b425fc1cc9d35f63d2e37b893bbc4a464134e194d995e27b.json',
        'bytes': 23853193, 'sha256': '39c5e0dc127ae3d7b425fc1cc9d35f63d2e37b893bbc4a464134e194d995e27b'},
    'primary': {'path': 'artifacts/project-static-evidence-a6fb7909318c253014daec86a32f70455ae77c8a0208cfeaedf2d4ec30f57508.json',
        'bytes': 9512434, 'sha256': 'a6fb7909318c253014daec86a32f70455ae77c8a0208cfeaedf2d4ec30f57508'},
    'fallback': {'path': 'artifacts/project-static-clang-fallback-0251cdd017b9c0c4257182651fcdcf2ae102dd931f8f39d8c62f164e5d80577f.json',
        'bytes': 2513517, 'sha256': '0251cdd017b9c0c4257182651fcdcf2ae102dd931f8f39d8c62f164e5d80577f'},
}


def prepare_capacity_inputs(client, scratch, records, load_store_reserve):
    """Exact retained a583 bytes via the same GET-only verified transport.

    This is a new runner's required input transfer, not a repeated historical
    reconciliation or native operation. Old private inputs stay private.
    """
    host = scratch / 'host'
    require(scratch.is_dir() and scratch.resolve(strict=True) == scratch
            and host.is_dir() and host.resolve(strict=True) == host
            and scratch.stat().st_mode & 0o077 == host.stat().st_mode & 0o077 == 0,
            'capacity_private_scratch')
    require(records.get('status') == 'PRIVATE_RETAINED_INPUTS_PREPARED'
            and 'capacity_sample' not in records, 'capacity_existing_preparation_required')
    preparation_path = host / 'preparation.json'
    require(preparation_path.is_file() and not preparation_path.is_symlink()
            and preparation_path.resolve(strict=True) == preparation_path
            and preparation_path.stat().st_mode & 0o077 == 0
            and 0 < preparation_path.stat().st_size <= MAX_META,
            'capacity_original_private_preparation')
    original_stat = preparation_path.stat()
    require(preparation_path.read_bytes() == canonical(records) + b'\n',
            'capacity_original_preparation_bytes')
    repository_id = 1282576027
    run = client.json('/repos/' + REPOSITORY + '/actions/runs/' + str(CAPACITY_INPUT_RUN) + '/attempts/1')
    require(run_identity(run, CAPACITY_INPUT_WORKFLOW, IMAGE_BRANCH, 'push', 'success',
                         repository_id, CAPACITY_INPUT_HEAD)
            and run['id'] == CAPACITY_INPUT_RUN, 'capacity_exact_run_binding')
    artifact = select_artifact(client, run, CAPACITY_INPUT_ARTIFACT['name'], repository_id, MAX_MEMBER)
    require(artifact['id'] == CAPACITY_INPUT_ARTIFACT['id']
            and artifact['size_in_bytes'] == CAPACITY_INPUT_ARTIFACT['bytes']
            and artifact['digest'] == 'sha256:' + CAPACITY_INPUT_ARTIFACT['sha256'],
            'capacity_exact_artifact_binding')
    total = sum(row['bytes'] for row in CAPACITY_INPUT_MEMBERS.values())
    allowance = artifact['size_in_bytes'] + total + MAX_META
    disk_proof = preflight(scratch, allowance, load_store_reserve)
    zip_path = host / 'capacity-sample.zip'
    expanded = host / 'capacity-sample-decoded'
    output = host / 'capacity-sample'
    require(not zip_path.exists() and not expanded.exists() and not output.exists(),
            'capacity_new_input_paths')
    transport = client.download(artifact, zip_path, MAX_MEMBER)
    require(zip_path.is_file() and not zip_path.is_symlink()
            and zip_path.stat().st_size == CAPACITY_INPUT_ARTIFACT['bytes']
            and sha(zip_path.read_bytes()) == CAPACITY_INPUT_ARTIFACT['sha256'],
            'capacity_whole_archive_anchor')
    expected = {row['path']: row for row in CAPACITY_INPUT_MEMBERS.values()}
    rows = extract_verified_zip(zip_path, expanded, 3, MAX_MEMBER, total, set(expected),
                                {name: row['bytes'] for name, row in expected.items()})
    require({row['path']: row for row in rows} == expected, 'capacity_exact_decoded_members')
    peak = scratch_bytes(scratch)
    output.mkdir(mode=0o700)
    refs = {}
    for key, row in CAPACITY_INPUT_MEMBERS.items():
        source = expanded / row['path']
        require(source.is_file() and not source.is_symlink()
                and source.resolve(strict=True) == source and source.stat().st_mode & 0o077 == 0,
                'capacity_private_decoded_member')
        source.rename(output / (key + '.json'))
        refs[key] = {'file': key + '.json', 'bytes': row['bytes'], 'sha256': row['sha256']}
    (expanded / 'artifacts').rmdir()
    expanded.rmdir()
    zip_path.unlink()
    proof = {'schema': 'nico.private.a583-capacity-input-transfer.v1',
             'run_id': CAPACITY_INPUT_RUN, 'run_attempt': 1, 'workflow_head': CAPACITY_INPUT_HEAD,
             'workflow_head_is_executed_worker_source_claimed': False,
             'artifact_id': artifact['id'], 'artifact_bytes': artifact['size_in_bytes'],
             'artifact_sha256': CAPACITY_INPUT_ARTIFACT['sha256'], 'members': refs,
             'whole_provider_and_pinned_archive_and_all_members_CRC_verified': True,
             'transport': transport, 'preflight': disk_proof,
             'observed_scratch_peak_bytes': peak,
             'native_execution': False, 'historical_reconciliation_repeated': False,
             'protected_report_request': False, 'new_storage_or_spend': False}
    records['capacity_sample'] = proof
    records['actual_observed_scratch_peak_bytes'] = max(records['actual_observed_scratch_peak_bytes'], peak)
    temporary = host / 'capacity-preparation.json.tmp'
    require(not temporary.exists() and not temporary.is_symlink(), 'capacity_new_preparation_temporary')
    write_private(temporary, records)
    current_stat = preparation_path.stat()
    require((current_stat.st_dev, current_stat.st_ino, current_stat.st_size, current_stat.st_mtime_ns)
            == (original_stat.st_dev, original_stat.st_ino, original_stat.st_size, original_stat.st_mtime_ns)
            and not preparation_path.is_symlink(), 'capacity_preparation_changed')
    temporary.replace(preparation_path)
    return proof


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--operation-source', required=True, type=Path)
    parser.add_argument('--recipe-source', required=True, type=Path)
    parser.add_argument('--scratch', required=True, type=Path)
    parser.add_argument('--load-store-reserve-bytes', required=True, type=int)
    parser.add_argument('--fallback-capacity-sample', action='store_true')
    args = parser.parse_args()
    for name in ('operation_source', 'recipe_source', 'scratch'):
        value = getattr(args, name).absolute()
        require(',' not in str(value) and (not value.exists() or value.resolve() == value), 'canonical_path')
        setattr(args, name, value)
    runner_temp = Path(os.environ.get('RUNNER_TEMP', '/nonexistent')).resolve(strict=True)
    require(args.scratch.is_relative_to(runner_temp) and args.scratch != runner_temp, 'private_runner_temp_only')
    token = os.environ.pop('GITHUB_TOKEN', '')
    client = ActionsClient(token)
    try:
        records = prepare(client, args.operation_source, args.recipe_source, args.scratch, args.load_store_reserve_bytes)
        if args.fallback_capacity_sample:
            prepare_capacity_inputs(client, args.scratch, records, args.load_store_reserve_bytes)
        # Aggregate status only. No paths, hashes, provider metadata or identifiers.
        print('{"status":"PRIVATE_RETAINED_INPUTS_PREPARED","native_execution":false}')
    finally:
        client._token = ''
        token = ''


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        code = str(error) if isinstance(error, PreparationError) else 'preparation_failed'
        if re.fullmatch(r'[a-z0-9_]+', code) is None:
            code = 'preparation_failed'
        print(json.dumps({'status': 'UNPROVEN', 'error_code': code, 'native_execution': False}))
        sys.exit(1)
