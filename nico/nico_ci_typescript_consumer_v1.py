"""Owned current-main CI evidence consumer; never executes assessed project code."""
from __future__ import annotations

from datetime import datetime, timezone
import io
import base64
import json
import time
import sys
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
import zipfile

import requests

from nico import nico_ci_typescript_github_v1 as authority
from nico.nico_ci_typescript_evidence_v1 import MAX_BYTES, REPOSITORY


class Capture:
    """One shared request/deadline budget for discovery, bytes and authentication."""
    def __init__(self, client, seconds):
        self.client = client
        self.headers = client.headers
        self.auth_mode = client.auth_mode
        self.deadline = time.monotonic() + min(seconds, 300)
        self.calls = 0

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        authority._require(remaining > 0 and self.calls < 1500, 'provider_capture_budget')
        return min(25, remaining)

    def get_json(self, url, params=None):
        self.remaining()
        self.calls += 1
        result = self.client.get_json(url, params)
        self.remaining()
        return result

    def get(self, path, params=None):
        value, error = self.get_json(authority.API + path, params)
        authority._require(not error and isinstance(value, dict), 'github_read_unavailable')
        return value

    def archive(self, artifact_id):
        # Only provider-issued HTTPS Azure artifact redirects are supported. Never
        # forward GitHub credentials to storage or follow arbitrary redirect chains.
        timeout = self.remaining(); self.calls += 1
        with requests.get(authority.API + f'/actions/artifacts/{artifact_id}/zip',
                          headers=self.headers, timeout=timeout, stream=True,
                          allow_redirects=False) as response:
            self.remaining()
            authority._require(response.status_code == 302, 'artifact_redirect_unavailable')
            location = response.headers.get('Location', '')
        parsed = urlsplit(location)
        authority._require(parsed.scheme == 'https' and parsed.hostname
                           and parsed.hostname.endswith('.blob.core.windows.net')
                           and not parsed.username and not parsed.password
                           and parsed.port in (None, 443), 'artifact_redirect_invalid')
        timeout = self.remaining(); self.calls += 1
        with requests.get(location, headers={'Accept': 'application/zip'}, timeout=timeout,
                          stream=True, allow_redirects=False) as response:
            authority._require(response.status_code == 200, 'artifact_download_unavailable')
            chunks = []; size = 0
            for chunk in response.iter_content(64 * 1024):
                self.remaining(); size += len(chunk)
                authority._require(size <= 3 * MAX_BYTES, 'archive_budget_exceeded')
                chunks.append(chunk)
            self.remaining()
            return b''.join(chunks)


def collect(client, target_sha, seconds, *, now=None):
    capture = Capture(client, seconds)
    authority._require(capture.auth_mode in {'github_app_installation', 'server_token'}
                       and bool(capture.headers.get('Authorization')), 'authenticated_github_client_required')
    authority._require(capture.get('/git/ref/heads/main').get('object', {}).get('sha') == target_sha,
                       'main_sha_not_current')
    runs = capture.get('/actions/workflows/node.js.yml/runs',
                       {'branch': 'main', 'head_sha': target_sha, 'per_page': 1}).get('workflow_runs')
    authority._require(isinstance(runs, list) and len(runs) == 1, 'latest_run_missing')
    run = runs[0]
    run_id = run.get('id'); attempt = run.get('run_attempt')
    authority._require(type(run_id) is int and run_id > 0 and type(attempt) is int and attempt > 0,
                       'provider_identifier_invalid')
    authority._require(run.get('head_sha') == target_sha and run.get('head_branch') == 'main'
                       and run.get('status') == 'completed', 'run_source_mismatch')
    expected = f'nico-typescript-{target_sha}-{run_id}-{attempt}'
    listing = capture.get(f'/actions/runs/{run_id}/artifacts', {'per_page': 100})
    rows = listing.get('artifacts')
    authority._require(isinstance(rows, list) and len(rows) <= 100
                       and listing.get('total_count') == len(rows), 'artifact_listing_incomplete')
    matches = [row for row in rows if row.get('name') == expected]
    authority._require(len(matches) == 1, 'artifact_missing_or_ambiguous')
    artifact = matches[0]; artifact_id = artifact.get('id')
    authority._require(type(artifact_id) is int and artifact_id > 0
                       and artifact.get('expired') is False
                       and type(artifact.get('size_in_bytes')) is int
                       and 0 < artifact['size_in_bytes'] <= 3 * MAX_BYTES, 'artifact_identity_mismatch')
    archive = capture.archive(artifact_id)
    result = authority._import_with_client(capture, archive, target_sha=target_sha,
        run_id=str(run_id), run_attempt=str(attempt), artifact_id=str(artifact_id),
        now=now or datetime.now(timezone.utc))
    capture.remaining()
    return result, archive


def _capture_bounded(target_sha, seconds):
    # Bound the trusted controller process, including slow-drip HTTP and client
    # initialization. Inherit its normal server environment; never copy credentials
    # into argv, output, or assessed project execution. No target commands run.
    with tempfile.TemporaryDirectory(prefix='nico-ci-typescript-') as directory:
        result = subprocess.run((sys.executable, '-m', 'nico.nico_ci_typescript_consumer_v1',
                                 target_sha, str(min(seconds, 300)), directory),
                                cwd=authority.ROOT, timeout=min(seconds, 300), shell=False,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, check=False)
        authority._require(result.returncode == 0, 'provider_capture_incomplete')
        output = Path(directory)
        authority._require((output/'result.json').stat().st_size <= MAX_BYTES
                           and (output/'archive.zip').stat().st_size <= 3*MAX_BYTES, 'archive_budget_exceeded')
        return json.loads((output/'result.json').read_text()), (output/'archive.zip').read_bytes()


def _retention_projection(value):
    from nico.scanner_evidence_pipeline_v1 import redact_payload, redact_text
    if isinstance(value, dict):
        result = {key: _retention_projection(item) for key, item in value.items()
                  if key != 'native_stderr_base64'}
        if 'native_stderr_base64' in value:
            raw = base64.b64decode(value['native_stderr_base64'], validate=True)
            result['native_stderr_redacted_text'] = redact_text(raw.decode('utf-8', errors='replace'))
            result['stderr_retention_encoding'] = 'decoded_utf8_redacted; original sha256 retained'
        return redact_payload(result)
    if isinstance(value, list):
        return [_retention_projection(item) for item in value]
    return redact_text(value) if isinstance(value, str) else value


def run(spec, workspace):
    from nico import scanner_evidence_pipeline_v1 as pipeline
    target_sha = pipeline._git_text(workspace, 'rev-parse', 'HEAD').lower()
    try:
        result, archive = _capture_bounded(target_sha, spec.timeout_seconds)
        if result.get('metadata_authenticated') is not True:
            return pipeline._unavailable(spec, 'Retained CI TypeScript evidence is incomplete or invalid.',
                                         source='authenticated_nico_postbuild_ci')
        # Keep all three validated native members, with ordinary scanner secret
        # redaction. Never hex-encode unredacted diagnostics to evade redaction.
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            members = {}
            for name in bundle.namelist():
                text = bundle.read(name).decode('utf-8')
                try:
                    value = json.loads(text)
                except ValueError:
                    value = text
                members[name] = _retention_projection(value)
        result = _retention_projection(result)
        # Assessment identities belong to durable scanner storage. GitHub IDs
        # must never occupy its run/customer/project/scan binding namespace.
        ci_result = {('ci_' + key if key in {
            'run_id', 'run_attempt', 'artifact_id', 'artifact_digest', 'workflow_id', 'source_sha'
        } else key): value for key, value in result.items()}
        raw = workspace.root / 'scanner-raw' / 'typescript-ci.json'
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text(json.dumps({'retention_projection':'Parsed and secret-redacted native members; embedded manifest hashes bind the original authenticated archive, not these projected copies', 'authenticated_import': result, 'members': members}), encoding='utf-8')
        blob = pipeline._raw_blob('typescript', raw, 'json')
        if result.get('status') != 'completed':
            payload = pipeline._unavailable(spec, 'Retained CI TypeScript capture did not complete.',
                                             source='authenticated_nico_postbuild_ci')
            payload.update(current_run=False, ci_run_id=result.get('run_id'), ci_run_attempt=result.get('run_attempt'),
                           ci_evidence=pipeline.redact_payload(result),
                           raw_artifact_capture_complete=True, raw_artifact_sha256=blob['sha256'],
                           raw_artifact_format='json', raw_artifact_bytes=blob['retained_bytes'],
                           _raw_artifact_blob=blob)
            return payload
        findings = []
        for diagnostic in result['diagnostics']:
            findings.append({**diagnostic, 'code': f"TS{diagnostic['code']}",
                             'file_path': diagnostic.get('file'),
                             'diagnostic_scope': 'file' if diagnostic.get('file') else 'project',
                             'severity': 'high' if diagnostic['category'] == 'Error' else 'low'})
        payload = {**ci_result, 'tool': 'typescript', 'category': spec.category,
            'returncode': result['raw_exit_code'], 'exit_code': result['raw_exit_code'], 'returncode_valid': True,
            'repository': REPOSITORY, 'commit_sha': target_sha,
            'production_scanner_integrated': True, 'score_override': False,
            'findings': findings, 'findings_count': len(findings), 'finding_count': len(findings),
            'verified_for_this_report': True, 'execution_observed_for_this_report': False,
            'current_run': False, 'command_intent': 'Import authenticated exact-main post-build CI evidence',
            'output_capture_complete': True, 'output_truncated': False,
            'raw_artifact_capture_complete': True, 'raw_artifact_sha256': blob['sha256'],
            'raw_artifact_format': 'json', 'raw_artifact_bytes': blob['retained_bytes'],
            'reason': '', 'failure_or_unavailable_reason': ''}
        payload = pipeline.redact_payload(payload)
        payload['artifact_hash'] = pipeline._sha256(json.dumps(payload, sort_keys=True).encode())
        payload['_raw_artifact_blob'] = blob
        return payload
    except Exception:
        # Do not leak provider URLs, credentials or diagnostic exceptions.
        return pipeline._unavailable(spec, 'Authenticated current-main CI TypeScript evidence is unavailable.',
                                     source='authenticated_nico_postbuild_ci')


if __name__ == '__main__':
    try:
        sha, seconds, directory = sys.argv[1:]
        result, archive = collect(authority._new_client(), sha, float(seconds))
        output = Path(directory)
        (output/'result.json').write_text(json.dumps(result), encoding='utf-8')
        (output/'archive.zip').write_bytes(archive)
    except Exception:
        sys.exit(1)
