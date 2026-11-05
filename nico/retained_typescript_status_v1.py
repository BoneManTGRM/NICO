"""Offline ordinary coverage for controller-imported, durably bound CI evidence.

This is not an authenticator for caller-supplied JSON. The canonical worker is
trusted to run the authenticated importer before persisting scanner results.
Recheck that protected result against its immutable redacted projection; do not
reconstruct AuthenticatedRun or claim that projected bytes are the original ZIP.
"""
from collections.abc import Mapping
import json
import re

from nico.nico_ci_typescript_evidence_v1 import REPOSITORY, SCHEMA, WORKFLOW
from nico.scanner_raw_artifact_storage_v1 import _jsonb_display_text

BASIS = 'authenticated_retained_typescript_ci'
SOURCE = 'authenticated_nico_postbuild_ci'


def verified_retained_typescript(record, binding, read) -> bool:
    if (binding.get('scanner_name') != 'typescript' or binding.get('repository') != REPOSITORY
        or any(record.get(key) != value for key, value in binding.items())
        or read.metadata.get('availability') != 'verified'
        or read.metadata.get('storage_backend') != 'postgres' or not read.raw
        or record.get('status') != 'completed' or record.get('execution_source') != SOURCE
        or record.get('execution_observed_for_this_report') is not False or record.get('current_run') is not False
        or any(record.get(key) is not True for key in ('metadata_authenticated', 'output_capture_complete',
            'returncode_valid', 'raw_artifact_retention_complete', 'verified_for_this_report'))):
        return False
    try:
        body = json.loads(read.raw)
        imported = body['authenticated_import']
        members = body['members']
        if set(members) != {'typescript.json', 'typescript.log', 'manifest.json'}:
            return False
        native_record, native, manifest = (members[name] for name in ('typescript.json', 'typescript.log', 'manifest.json'))
        if not all(isinstance(value, Mapping) for value in (imported, native_record, native, manifest)):
            return False
        if (imported.get('metadata_authenticated') is not True or imported.get('scanner') != 'typescript'
            or imported.get('execution_source') != SOURCE or imported.get('status') != 'completed'
            or imported.get('source_sha') != binding['commit_sha']
            or record.get('ci_source_sha') != binding['commit_sha']):
            return False
        for key in ('run_id', 'run_attempt', 'artifact_id', 'workflow_id'):
            value = imported.get(key)
            if (type(value) not in (str, int) or not re.fullmatch(r'[1-9][0-9]*', str(value))
                or record.get('ci_' + key) != value):
                return False
        digest = imported.get('artifact_digest')
        if (not isinstance(digest, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest)
            or record.get('ci_artifact_digest') != digest):
            return False
        if (native_record.get('repository') != REPOSITORY
            or native_record.get('source_sha') != binding['commit_sha']
            or native_record.get('workflow_sha') != binding['commit_sha']
            or native_record.get('workflow_ref') != f'{REPOSITORY}/{WORKFLOW}@refs/heads/main'
            or native_record.get('event') not in {'push', 'workflow_dispatch'}
            or any(native_record.get(key) != imported[key] for key in ('run_id', 'run_attempt', 'build_outcome'))
            or imported.get('build_outcome') not in {'success', 'failure'}):
            return False
        if (native_record.get('schema') != SCHEMA or native.get('schema') != SCHEMA
            or manifest.get('schema') != SCHEMA or native_record.get('status') != 'completed'
            or native_record.get('capture_complete') is not True
            or native_record.get('capture_timed_out') is not False or native_record.get('capture_truncated') is not False
            or any(native_record.get(key) != value for key, value in native.items())):
            return False
        hashes = manifest.get('files', {})
        if (set(hashes) != {'typescript.json', 'typescript.log'}
            or any(not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value) for value in hashes.values())
            or native_record.get('native_stdout_sha256') != hashes['typescript.log']):
            return False
        # Original member hashes are provenance, not hashes of redacted JSON.
        # Durable read verification above binds the actual projected bytes.
        diagnostics = imported.get('diagnostics')
        clean = imported.get('clean')
        if (not isinstance(diagnostics, list) or type(clean) is not bool
            or any(not isinstance(d, Mapping) or type(d.get('code')) is not int
                   or d.get('category') not in {'Error', 'Warning', 'Suggestion', 'Message'}
                   or not isinstance(d.get('message'), str) for d in diagnostics)
            or clean != (not any(d['category'] == 'Error' for d in diagnostics))):
            return False
        display_fields = ('clean', 'diagnostics', 'effective_configuration', 'configuration_limitations')
        for key in display_fields:
            if key not in imported or imported[key] != native_record.get(key):
                return False
        findings = [{**d, 'code': f"TS{d['code']}", 'file_path': d.get('file'),
                     'diagnostic_scope': 'file' if d.get('file') else 'project',
                     'severity': 'high' if d['category'] == 'Error' else 'low'} for d in diagnostics]
        # Raw import/native values must agree exactly. Only the protected worker
        # record uses persistence's display escaping; never normalize raw bytes.
        expected_display = _jsonb_display_text({
            **{key: imported[key] for key in display_fields},
            'findings': findings, 'checked_project_scope': imported.get('checked_project_scope'),
        })
        if any(record.get(key) != expected_display[key] for key in (*display_fields, 'findings', 'checked_project_scope')):
            return False
        if (record.get('findings_count') != len(findings)
            or record.get('finding_count') != len(findings)):
            return False
        if not native or not imported.get('checked_project_scope'):
            return False
        expected_exit = 0 if clean else 1
        return (all(type(value) is int and value == expected_exit for value in (
                    imported.get('raw_exit_code'), native_record.get('raw_exit_code'), record.get('returncode'), record.get('exit_code')))
                and imported.get('check_outcome') == ('success' if clean else 'failure'))
    except (ValueError, KeyError, TypeError, AttributeError):
        return False
