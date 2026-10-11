"""Shared-envelope expiry must preserve evidence and never imply completion."""
import base64
from copy import deepcopy
import hashlib
import json

import pytest

from nico import assessment_cpp_clang_fallback as clang
from nico import assessment_cpp_project_static as static
from nico import assessment_cpp_static_environment as env
from nico.assessment_cpp_project_compiler import _canonical
from tests.test_cpp_header_incomplete_fallback import owned_header_gap, native_response
from tests.test_cpp_project_static_stage import StaticDocker
from tests.test_cpp_static_environment import evidence as environment_evidence, observed


def run_shared_stage(tmp_path, monkeypatch, *, expired=False, cancelled=False):
    req, _, raw, primary, (database, targets, snapshot, craw) = owned_header_gap(tmp_path)
    _, value = native_response(tmp_path, req, primary)
    clock = [0.0]
    dispatched = [False]
    lease_checks = []
    def owner_checkpoint():
        lease_checks.append(dispatched[0])
        if cancelled and dispatched[0]:
            raise ValueError('owned_lease_lost')
    monkeypatch.setattr(static.time, 'monotonic', lambda: clock[0])
    class OwnedDocker(StaticDocker):
        def __call__(self, argv, **kwargs):
            if env.ENV_PROGRAM in argv:
                er = json.loads(kwargs['input_bytes']); data = environment_evidence(er)
                data['schema'] = 'nico.cpp-static-environment.v2'
                for q in data['queries'].values():
                    q['predefines'] = observed(base64.b64decode(q['predefines']['output']) + b'#define __cplusplus 202002L\n')
                output = _canonical(data)
            elif static.PROGRAM in argv:
                assert json.loads(kwargs['input_bytes']) == req
                output = raw; clock[0] = 700.0
            elif clang.PROGRAM in argv:
                dispatched[0] = True
                # All population and per-unit maxima remain unchanged. Only
                # the remaining shared envelope may be allocated to the child.
                assert json.loads(kwargs['input_bytes'])['limits'] == {'wall_seconds':480, 'case_seconds':120, 'parallel':2}
                if not expired:
                    assert argv[-1] == '310000'
                kwargs['checkpoint']()
                if expired:
                    clock[0] = 1020.0
                    kwargs['checkpoint']()
                value['wall_budget_ms'] = int(argv[-1])
                output = _canonical(value)
            else:
                return super().__call__(argv, **kwargs)
            self.calls.append((argv, kwargs))
            return dict(exit_code=124 if expired and clang.PROGRAM in argv else 0,
                timed_out=expired and clang.PROGRAM in argv, output_truncated=False, output=output)
    root = tmp_path / 'source'; root.mkdir(); (root/'unit.cpp').write_bytes(b'int value(){return VALUE;}\n')
    artifacts = {}; saved = []
    def sink(key, data):
        artifacts[key] = data; digest = hashlib.sha256(data).hexdigest()
        return dict(path='artifacts/'+key+'-'+digest+'.json', bytes=len(data), sha256=digest)
    result = static.run_project_static_stage(root, targets, 'sha256:'+'a'*64, database, snapshot, craw,
        compiler_environment=True, header_provenance=True, collect_completed_compiler_failures=True,
        command=OwnedDocker(targets), retain_artifact=sink, retain=lambda r:saved.append(deepcopy(r)),
        checkpoint=owner_checkpoint)
    assert lease_checks and (True in lease_checks if dispatched[0] else True)
    return result, artifacts, saved


def test_shared_remaining_budget_reaches_child_without_changing_population_or_maxima(tmp_path, monkeypatch):
    result, artifacts, _ = run_shared_stage(tmp_path, monkeypatch)
    assert result['collection_complete'], result['error']
    assert result['execution_budget_seconds'] == 1020 and result['wall_budget_seconds'] == 1030
    assert 'project-static-clang-fallback' in artifacts


def test_shared_deadline_retains_returned_fallback_bytes_before_rejecting(tmp_path, monkeypatch):
    result, artifacts, saved = run_shared_stage(tmp_path, monkeypatch, expired=True)
    assert result['error'] == 'worker_project_static_stage_deadline'
    assert not result['complete'] and not result['collection_complete'] and not result['production_qualified']
    assert 'project-static-clang-fallback' in artifacts, 'shared expiry discarded returned native bytes'
    operation = next(o for o in result['operations'] if o['id']=='project-static-clang-fallback')
    assert operation['timed_out'] and operation['exit_code']==124
    assert operation['output_artifact']['sha256'] == hashlib.sha256(artifacts['project-static-clang-fallback']).hexdigest()
    assert result['cleanup_verified'] and saved[-1] == result


def test_owner_lease_loss_still_interrupts_fallback_and_prevents_completion(tmp_path, monkeypatch):
    result, artifacts, saved = run_shared_stage(tmp_path, monkeypatch, cancelled=True)
    assert not result['complete'] and not result['collection_complete']
    assert result['error'] == 'worker_project_static_stage_failed'
    assert 'project-static-clang-fallback' not in artifacts
    assert result['cleanup_verified'] and saved[-1] == result


@pytest.mark.parametrize('budget', [-1, 0, 480001, True, '100', 1.0])
def test_child_rejects_invalid_or_increased_shared_budget_before_any_execution(budget):
    req = {'schema':'nico.cpp-clang-fallback-request.v7', 'limits':dict(clang.LOW_CONTENTION_LIMITS)}
    with pytest.raises(ValueError, match='worker_clang_fallback_request_invalid'):
        clang.collect_clang_fallback(req, wall_budget_ms=budget)


@pytest.mark.parametrize('budget', ['0', '-1', '1', '2', '479999', '480001', '310000.0', '0310000', 'nan', '310000;echo unsafe'])
def test_qualification_transport_rejects_changed_or_malformed_child_allocation(tmp_path, budget):
    from nico.assessment_cpp_collection import validate_project_collection
    from tests.test_cpp_completed_collection_projection import qualification_bundle
    receipt, read, kwargs, _ = qualification_bundle(tmp_path, failing=True)
    assert validate_project_collection(receipt, read, **kwargs)['collection_complete']
    op = next(o for o in receipt['probe']['project_static_stage']['operations']
        if o['id'] == 'project-static-clang-fallback')
    assert op['invocation'][-1].isdigit()
    op['invocation'][-1] = budget
    with pytest.raises(ValueError, match='qualification_collection_transport_invalid'):
        validate_project_collection(receipt, read, **kwargs)


def test_cli_passes_only_canonical_bounded_allocation_to_collector(monkeypatch, capsys):
    import io
    import sys
    from types import SimpleNamespace
    called = []
    def collect(request, **kwargs):
        called.append((request, kwargs)); return {'owned':'result'}
    monkeypatch.setattr(clang, 'collect_clang_fallback', collect)
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(b'{}')))
    monkeypatch.setattr(sys, 'argv', ['-c', '310000'])
    clang.run_clang_fallback()
    assert called == [({}, {'wall_budget_ms':310000})]
    assert json.loads(capsys.readouterr().out) == {'owned':'result'}
