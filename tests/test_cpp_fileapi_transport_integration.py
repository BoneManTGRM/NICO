"""Versioned installed integration with an explicitly substituted Docker boundary.

The native 18c fixture stays immutable. Rebased reply metadata below is a
controlled adapter response; it does not qualify a compiler, image or target.
"""
import base64
from copy import deepcopy
import hashlib
import json

import pytest

from nico.assessment_cpp_configuration_probe import probe_project_configuration, READ_PROGRAM
from nico.assessment_cpp_fileapi_membership import QUERY_PROGRAM, CAPTURE_PROGRAM, EMPTY_SHA, QUERY_NAMES
from nico.assessment_cpp_baseline_evidence import retained_baseline_bytes, validate_retained_baseline
from nico.assessment_cpp_configure_first_execution import summarize_probe
from nico.assessment_worker_receipts import canonical_bytes
from scripts.qualify_cpp_project_configuration import persist_project_artifact
from tests.test_cpp_baseline_execution import Native, contract
from tests.test_cpp_configure_first_execution import ref
from tests.test_cpp_fileapi_target_membership import FIXTURE, owned


def adapter_data(client, cache_hash):
    capsule, database, targets, kwargs = owned()
    def rebase(value):
        return value.replace(kwargs['source_root'], '/work/source').replace(kwargs['build_root'], '/work/build')
    database = rebase(database.decode()).replace(kwargs['compiler_paths']['C'], '/usr/local/bin/gcc').encode()
    files = {}
    for name, row in capsule['files'].items():
        value = json.loads(rebase(base64.b64decode(row['data']).decode()))
        if name.startswith('index-'):
            value['reply'] = {client: value['reply'][capsule['client']]}
        if name.startswith('toolchains-'):
            value['toolchains'][0]['compiler'].update(path='/usr/local/bin/gcc', version='14.2.0')
        raw = canonical_bytes(value)
        files[name] = dict(data=base64.b64encode(raw).decode(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    capsule.update(source_root='/work/source', build_root='/work/build', client=client,
        files=files, cache_sha256=cache_hash, database_sha256=hashlib.sha256(database).hexdigest())
    return capsule, database, targets


class FileAPIDocker(Native):
    def __init__(self, targets, failed=False, malformed=False):
        super().__init__(targets, 'target_failure' if failed else None)
        self.malformed = malformed
        self.capture = None
        self.database = adapter_data('client-nico-placeholder', None)[1]

    def __call__(self, args, **kwargs):
        raw = None
        if QUERY_PROGRAM in args:
            raw = canonical_bytes({'client': args[-1], 'query': {q: EMPTY_SHA for q in QUERY_NAMES}})
        elif CAPTURE_PROGRAM in args:
            request = json.loads(kwargs['input_bytes'])
            capsule, database, targets = adapter_data(request['client'], request['cache_sha256'])
            assert database == self.database and request['source_targets'] == targets
            assert request['database_sha256'] == hashlib.sha256(database).hexdigest()
            if self.malformed:
                del capsule['files'][next(k for k in capsule['files'] if k.startswith('target-hidden-'))]
            raw = canonical_bytes(capsule)
            self.capture = raw
        elif READ_PROGRAM in args and '/work/build/compile_commands.json' in args:
            raw = canonical_bytes({'data': base64.b64encode(self.database).decode(), 'truncated': False})
        if raw is None:
            return super().__call__(args, **kwargs)
        self.calls.append((args, kwargs))
        return dict(exit_code=0, timed_out=False, output_truncated=False, output=raw)


def run_case(tmp_path, *, failed=False, malformed=False):
    source, output = tmp_path / 'source', tmp_path / 'retained'
    source.mkdir(); output.mkdir()
    targets = owned()[2]
    for name in targets:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((FIXTURE / 'source' / name).read_bytes())
    docker = FileAPIDocker(targets, failed, malformed)
    baseline = contract()
    baseline['compilation_database_sha256'] = hashlib.sha256(docker.database).hexdigest()
    result = probe_project_configuration(source, targets, 'sha256:' + 'a' * 64,
        project_options={'BUILD_TESTS': 'ON'}, baseline_execution=baseline, command=docker,
        capture_enabled_targets=True,
        retain_artifact=lambda key, raw: persist_project_artifact(output, key, raw))
    configuration = dict(schema='nico.cpp-configure-first-contract.v4', baseline_execution=baseline)
    return result, targets, configuration, docker, output


@pytest.mark.parametrize('failed', [False, True])
def test_versioned_baseline_keeps_missing_context_and_real_outcome(failed, tmp_path):
    probe, targets, configuration, docker, output = run_case(tmp_path, failed=failed)
    assert probe['schema'] == 'nico.cpp-project-configuration-probe.v8'
    assert probe['status'] == 'BASELINE_EXECUTED' and probe['tests_passed'] is (not failed)
    assert probe['configured_invocations'] == 1
    membership = probe['enabled_target_membership']
    assert membership['configured_context_count'] == 2
    assert membership['database_membership_complete'] is False
    assert [row['file'] for row in membership['missing_database_contexts']] == ['/work/source/hidden.c']
    ids = [row['id'] for row in probe['operations']]
    assert ids.index('fileapi-query') < ids.index('configure')
    assert ids.index('project-enabled-targets') < ids.index('baseline-build')
    capture = probe['enabled_target_capture']
    assert (output / capture['path']).read_bytes() == docker.capture
    raw = retained_baseline_bytes(probe, targets, configuration, 'sha256:' + 'a' * 64)
    assert json.loads(raw)['schema'] == 'nico.cpp-baseline-evidence.v2'
    native = summarize_probe(probe, targets, {'project-enabled-targets': ref('project-enabled-targets', docker.capture)})
    native.update(project_options=probe['project_options'])
    baseline = validate_retained_baseline(raw, targets, configuration, 'sha256:' + 'a' * 64,
        native, membership_raw=docker.capture)
    assert baseline['collection_complete'] is True  # Baseline collection only.
    assert baseline['tests_passed'] is (not failed)
    assert baseline['native_exit_code'] == (8 if failed else 0)
    assert native['complete_execution'] is False and native['context_argv_binding_verified'] is False
    for mutation in ('missing_capture', 'corrupt_capture', 'false_digest', 'wrong_query_order', 'wrong_argv'):
        value, summary, capture_raw = json.loads(raw), deepcopy(native), docker.capture
        if mutation == 'missing_capture': capture_raw = None
        elif mutation == 'corrupt_capture': capture_raw += b' '
        elif mutation == 'false_digest': summary['enabled_target_capture_sha256'] = '0' * 64
        elif mutation == 'wrong_query_order':
            ops = value['probe']['operations']; ops[11], ops[12] = ops[12], ops[11]
        else:
            row = next(x for x in value['probe']['operations'] if x['id'] == 'project-enabled-targets')
            row['invocation'].append('--trust-summary')
        with pytest.raises(ValueError):
            validate_retained_baseline(canonical_bytes(value), targets, configuration,
                'sha256:' + 'a' * 64, summary, membership_raw=capture_raw)


def test_malformed_capture_is_retained_before_parser_rejection(tmp_path):
    probe, _, _, docker, output = run_case(tmp_path, malformed=True)
    assert probe['status'] == 'UNPROVEN'
    assert probe['enabled_target_membership'] is None
    assert probe['enabled_target_capture'] is not None
    assert (output / probe['enabled_target_capture']['path']).read_bytes() == docker.capture
    assert probe['error'] == 'worker_configuration_probe_fileapi_invalid'
    assert probe['cleanup_verified'] is True
    assert not any(row['id'] == 'baseline-build' for row in probe['operations'])
