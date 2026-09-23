"""Anonymous GitHub adapter for the exact, already-authorized input population.

The GitHub HTTPS commit/tree responses establish membership; independently
frozen SHA256 values bind original blob bytes. This is not a local Git-object
verification receipt, a full checkout, or proof of an analyzed denominator.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import multiprocessing
import os
from pathlib import Path, PurePosixPath
import re
import tarfile
import tempfile
import time
from urllib.parse import quote, urlsplit

import requests

from nico.assessment_worker_consumer import _unique_object

MAX_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_EXPANDED_BYTES = 128 * 1024 * 1024
ARCHIVE_MINIMUM_POPULATION = 32


def _download_child(url, destination, limit):
    session = requests.Session()
    session.trust_env = False
    response = None
    try:
        accept = 'application/octet-stream' if urlsplit(url).netloc == 'codeload.github.com' else 'application/vnd.github+json'
        response = session.get(url, headers={'Accept': accept,
            'Accept-Encoding': 'identity'}, timeout=(2, 5), allow_redirects=False, stream=True)
        if response.status_code != 200 or response.headers.get('Content-Encoding', 'identity') != 'identity':
            raise ValueError('worker_source_http_rejected')
        size = 0
        with Path(destination).open('xb') as handle:
            for chunk in response.iter_content(chunk_size=65536):
                size += len(chunk)
                if size > limit:
                    raise ValueError('worker_source_budget_exceeded')
                handle.write(chunk)
    except Exception:
        Path(destination).unlink(missing_ok=True)
        # No response content or exception (which may contain URLs) is logged.
    finally:
        if response is not None:
            response.close()
        session.close()


def download_public(url, destination, *, limit, checkpoint, deadline):
    parsed = urlsplit(url)
    archive = parsed.netloc == 'codeload.github.com'
    maximum = MAX_ARCHIVE_BYTES if archive else MAX_BYTES
    if (parsed.scheme != 'https' or parsed.netloc not in {
                'api.github.com', 'raw.githubusercontent.com', 'codeload.github.com'}
            or parsed.fragment or type(limit) is not int or not 1 <= limit <= maximum
            or (archive and (parsed.query or not re.fullmatch(
                r'/[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+/tar\.gz/[0-9a-f]{40}', parsed.path)))):
        raise ValueError('worker_source_request_invalid')
    checkpoint()
    deadline = min(deadline, time.monotonic() + 30)
    process = multiprocessing.get_context('spawn').Process(target=_download_child, args=(url, destination, limit))
    complete = False
    try:
        process.start()
        while process.is_alive():
            checkpoint()
            if time.monotonic() >= deadline:
                raise ValueError('worker_source_deadline')
            process.join(0.1)
        checkpoint()
        if (time.monotonic() >= deadline or process.exitcode != 0 or not destination.is_file()
                or destination.is_symlink() or destination.stat().st_size > limit):
            raise ValueError('worker_source_download_failed')
        complete = True
    finally:
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
                process.join(0.25)
            if process.is_alive():
                process.kill()
            process.join(1)
            process.close()
        # A terminated child cannot recreate a partial file after cleanup.
        if not complete:
            destination.unlink(missing_ok=True)


def _archive_fits(entries, maximum):
    """An archive contains the whole tree, not just the selected population."""
    total = 0
    for entry in entries.values():
        if entry.get('type') in {'tree', 'commit'}:
            continue
        size = entry.get('size')
        if (entry.get('type') != 'blob' or type(size) is not int
                or not 0 <= size <= maximum):
            return False
        total += size
        if total > maximum:
            return False
    return True


def _materialize_archive(name, revision, stage, entries, population, inputs,
                         checkpoint, deadline, download):
    """Stream a pinned GitHub archive; never extract paths, links or special files.

    All regular members are checked against the HTTPS-pinned tree's Git blob
    hashes. Only frozen selected bytes are written, with an independent SHA256
    check. Tar padding, extended headers and trailing data share one expansion
    budget. No failed archive silently falls back to a different acquisition.
    """
    archive_path = stage / 'source.tar.gz'
    url = 'https://codeload.github.com/' + name + '/tar.gz/' + revision
    download(url, archive_path, limit=MAX_ARCHIVE_BYTES, checkpoint=checkpoint, deadline=deadline)
    if (archive_path.is_symlink() or not archive_path.is_file()
            or not 0 < archive_path.stat().st_size <= MAX_ARCHIVE_BYTES):
        raise ValueError('worker_source_archive_budget')
    with archive_path.open('rb') as handle:
        archive_hash = hashlib.file_digest(handle, 'sha256').hexdigest()
    prefix = name.rsplit('/', 1)[1] + '-' + revision
    seen, materialized = set(), set()
    files = 0

    class ExpandedReader:
        def __init__(self, stream):
            self.stream, self.count = stream, 0

        def read(self, size):
            checkpoint()
            if time.monotonic() >= deadline:
                raise ValueError('worker_source_deadline')
            raw = self.stream.read(min(size, 65536))
            self.count += len(raw)
            if self.count > MAX_ARCHIVE_EXPANDED_BYTES:
                raise ValueError('worker_source_archive_expansion_budget')
            checkpoint()
            return raw

    try:
        with gzip.open(archive_path, 'rb') as compressed:
            reader = ExpandedReader(compressed)
            with tarfile.open(fileobj=reader, mode='r|', bufsize=65536) as archive:
                for member in archive:
                    checkpoint()
                    if time.monotonic() >= deadline:
                        raise ValueError('worker_source_deadline')
                    path = member.name.rstrip('/') if member.isdir() else member.name
                    if path in seen or len(seen) > len(entries):
                        raise ValueError('worker_source_archive_population_invalid')
                    seen.add(path)
                    if path == prefix:
                        if not member.isdir():
                            raise ValueError('worker_source_archive_root_invalid')
                        continue
                    if not path.startswith(prefix + '/'):
                        raise ValueError('worker_source_archive_path_invalid')
                    path = path[len(prefix) + 1:]
                    if (not path or len(path) > 1000 or path.startswith('/') or ':' in path or '\\' in path
                            or PurePosixPath(path).as_posix() != path
                            or any(part in {'.', '..', '.git'} for part in path.split('/'))
                            or any(ord(char) < 32 or ord(char) == 127 for char in path)):
                        raise ValueError('worker_source_archive_path_invalid')
                    entry = entries.get(path, {})
                    if member.isdir():
                        if entry.get('type') not in {'tree', 'commit'}:
                            raise ValueError('worker_source_archive_population_invalid')
                        continue
                    # Git symlinks may be present outside the selected population.
                    # Verify their stored link text but never create a filesystem link.
                    if member.issym() and path not in population and entry.get('mode') == '120000':
                        raw = member.linkname.encode('utf-8')
                        digest = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw,
                                              usedforsecurity=False).hexdigest()
                        if len(raw) != entry.get('size') or digest != entry.get('sha'):
                            raise ValueError('worker_source_digest_mismatch')
                        continue
                    if (member.type not in {tarfile.REGTYPE, tarfile.AREGTYPE} or member.sparse is not None
                            or entry.get('type') != 'blob' or entry.get('mode') not in {'100644', '100755'}
                            or type(entry.get('size')) is not int or member.size != entry['size']):
                        raise ValueError('worker_source_archive_type_or_size_invalid')
                    selected = path in population
                    output = inputs / path if selected else None
                    if output is not None:
                        output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    blob = hashlib.sha1(b'blob ' + str(member.size).encode() + b'\0', usedforsecurity=False)
                    sha256 = hashlib.sha256()
                    count = 0
                    handle = output.open('xb') if output is not None else None
                    try:
                        with archive.extractfile(member) as content:
                            while True:
                                checkpoint()
                                if time.monotonic() >= deadline:
                                    raise ValueError('worker_source_deadline')
                                raw = content.read(65536)
                                if not raw:
                                    break
                                if selected and count == 0 and raw.startswith(b'version https://git-lfs.github.com/spec/v1'):
                                    raise ValueError('worker_source_type_unsupported')
                                count += len(raw)
                                if count > member.size:
                                    raise ValueError('worker_source_archive_type_or_size_invalid')
                                blob.update(raw); sha256.update(raw)
                                if handle is not None:
                                    handle.write(raw)
                    finally:
                        if handle is not None:
                            handle.close()
                    if (count != member.size or blob.hexdigest() != entry.get('sha')
                            or (selected and sha256.hexdigest() != population[path])):
                        raise ValueError('worker_source_digest_mismatch')
                    files += 1
                    if selected:
                        output.chmod(0o555 if entry['mode'] == '100755' else 0o444)
                        materialized.add(path)
                # Consume all buffered and remaining padding, reaching gzip EOF
                # so a truncated trailer, concatenated tar or expansion bomb fails.
                while True:
                    trailing = archive.fileobj.read(65536)
                    if not trailing:
                        break
                    if any(trailing):
                        raise ValueError('worker_source_archive_trailing_data')
            if materialized != set(population):
                raise ValueError('worker_source_archive_population_incomplete')
    except (tarfile.TarError, OSError, EOFError, UnicodeError):
        raise ValueError('worker_source_archive_invalid') from None
    return {'kind': 'github_exact_commit_tar', 'archive_sha256': archive_hash,
        'compressed_bytes': archive_path.stat().st_size, 'expanded_bytes': reader.count,
        'archive_files': files, 'selected_files': len(materialized), 'network_requests': 3}


def acquire_public_github_inputs(job, root, checkpoint, *, download=download_public):
    identity = job['identity']
    repository = identity['repository_id']
    parsed = urlsplit(repository)
    match = re.fullmatch(r'/([A-Za-z0-9_-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?', parsed.path)
    revision = identity['revision']
    if (parsed.scheme != 'https' or parsed.netloc != 'github.com' or not match
            or parsed.query or parsed.fragment or match.group(2) in {'.', '..'}
            or not re.fullmatch(r'[0-9a-f]{40}', revision)
            or job.get('source_access') != {'mode': 'anonymous_public', 'credential_used': False}
            or job['source_access']['credential_used'] is not False):
        raise ValueError('worker_source_repository_unsupported')
    contract = job['contract']
    maximum = MAX_BYTES
    if contract.get('profile') == 'cpp-full-project-v1':
        from nico.assessment_worker_receipts import validate_contract
        contract = validate_contract(contract)
        maximum = contract['configuration']['source_byte_limit']
    population = dict(contract['targets'])
    if not 1 <= len(population) <= 20000:
        raise ValueError('worker_source_population_invalid')
    for path, digest in population.items():
        if (not isinstance(path, str) or not path or len(path) > 1000
                or path.startswith('/') or ':' in path or '\\' in path
                or PurePosixPath(path).as_posix() != path
                or any(part in {'.', '..', '.git'} for part in path.split('/'))
                or any(ord(char) < 32 or ord(char) == 127 for char in path)
                or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest)):
            raise ValueError('worker_source_population_invalid')
    root = Path(root).resolve(strict=True)
    if root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o022:
        raise ValueError('worker_source_destination_invalid')
    destination = root / 'source'
    if destination.exists() or destination.is_symlink():
        raise ValueError('worker_source_destination_exists')
    deadline = time.monotonic() + min(300, max(0, job['deadline_epoch'] - time.time()))
    name = match.group(1) + '/' + match.group(2)
    api = 'https://api.github.com/repos/' + name + '/git/'
    checkpoint()
    with tempfile.TemporaryDirectory(prefix='.nico-source-', dir=root) as temporary:
        stage = Path(temporary)
        def metadata(url, filename, limit):
            output = stage / filename
            download(url, output, limit=limit, checkpoint=checkpoint, deadline=deadline)
            value = json.loads(output.read_bytes(), object_pairs_hook=_unique_object)
            if not isinstance(value, dict):
                raise ValueError('worker_source_metadata_invalid')
            return value
        commit = metadata(api + 'commits/' + revision, 'commit.json', 1024 * 1024)
        tree_sha = (commit.get('tree') or {}).get('sha', '')
        if commit.get('sha') != revision or not re.fullmatch(r'[0-9a-f]{40}', tree_sha):
            raise ValueError('worker_source_revision_mismatch')
        tree = metadata(api + 'trees/' + tree_sha + '?recursive=1', 'tree.json', 8 * 1024 * 1024)
        if tree.get('sha') != tree_sha or tree.get('truncated') is not False or not isinstance(tree.get('tree'), list):
            raise ValueError('worker_source_tree_incomplete')
        entries = {}
        for entry in tree['tree']:
            path = entry.get('path') if isinstance(entry, dict) else None
            if not isinstance(path, str) or path in entries:
                raise ValueError('worker_source_tree_invalid')
            entries[path] = entry
        total = 0
        for path in population:
            entry = entries.get(path, {})
            size = entry.get('size')
            if (entry.get('mode') not in {'100644', '100755'} or entry.get('type') != 'blob'
                    or not re.fullmatch(r'[0-9a-f]{40}', entry.get('sha', ''))
                    or type(size) is not int or not 0 <= size <= MAX_BYTES):
                raise ValueError('worker_source_type_or_size_invalid')
            total += size
        if total > maximum:
            raise ValueError('worker_source_budget_exceeded')
        inputs = stage / 'inputs'
        inputs.mkdir(mode=0o700)
        transport = None
        use_archive = (contract.get('profile') == 'cpp-full-project-v1'
            and len(population) >= ARCHIVE_MINIMUM_POPULATION and _archive_fits(entries, maximum))
        if use_archive:
            transport = _materialize_archive(name, revision, stage, entries, population, inputs,
                                             checkpoint, deadline, download)
        else:
            for path, digest in sorted(population.items()):
                checkpoint()
                entry = entries[path]
                output = inputs / path
                output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                url = 'https://raw.githubusercontent.com/' + name + '/' + revision + '/' + quote(path, safe='/')
                download(url, output, limit=max(1, entry['size']), checkpoint=checkpoint, deadline=deadline)
                raw = output.read_bytes()
                oid = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw, usedforsecurity=False).hexdigest()
                if len(raw) != entry['size'] or hashlib.sha256(raw).hexdigest() != digest or oid != entry['sha']:
                    raise ValueError('worker_source_digest_mismatch')
                if raw.startswith(b'version https://git-lfs.github.com/spec/v1'):
                    raise ValueError('worker_source_type_unsupported')
                output.chmod(0o555 if contract.get('profile') == 'cpp-full-project-v1' and entry['mode'] == '100755' else 0o444)
        checkpoint()
        if time.monotonic() >= deadline:
            raise ValueError('worker_source_deadline')
        destination.mkdir(mode=0o700)
        os.replace(inputs, destination)
    return destination, {'schema': 'nico.github_https_input_materialization.v1',
        'commit_sha': revision, 'tree_sha': tree_sha, 'inputs': population,
        'population_sha256': hashlib.sha256(json.dumps(population, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'required_count': len(population), 'materialized_count': len(population), 'source_bytes': total,
        'analyzed_count': None, 'authorized': False, 'assessed_code_executed': False,
        **({'transport': transport} if transport is not None else {})}
