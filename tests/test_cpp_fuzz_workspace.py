"""Capability-free fuzz-directory setup; mocked calls do not prove isolation."""
from copy import deepcopy
import json

import pytest

from nico.assessment_cpp_fuzz_runtime import (
    SETUP_PROGRAM, RUNTIME_SETUP_PROGRAM, SEAL_SETUP_PROGRAM, prepare_workspace,
)
from tests.test_cpp_bounded_fuzz import plan


class SetupTransport:
    def __init__(self, *, altered=None):
        self.calls = []
        self.altered = altered

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if SETUP_PROGRAM in argv:
            assert '--user=0:0' in argv
            assert kwargs['data']
            return b'wrong' if self.altered == 'root' else b'fuzz_snapshot_destinations_ready\n'
        if SEAL_SETUP_PROGRAM in argv:
            assert '--user=0:0' in argv
            return b'wrong' if self.altered == 'seal' else b'fuzz_runtime_population_sealed\n'
        assert RUNTIME_SETUP_PROGRAM in argv
        uid = int(next(arg.split('=')[1].split(':')[0] for arg in argv if arg.startswith('--user=')))
        proof = {'name': argv[-1], 'uid': uid, 'gid': uid}
        if self.altered in proof:
            proof[self.altered] = 'unexpected'
        return json.dumps(proof).encode()


def test_setup_uses_the_final_runtime_uids_without_chown_or_new_capabilities():
    transport = SetupTransport()
    p = plan(); before = deepcopy(p)
    prepare_workspace(transport, 'owned-container', p)
    calls = transport.calls
    assert SETUP_PROGRAM in calls[0][0]
    assert SEAL_SETUP_PROGRAM in calls[-1][0]
    assert [(args[-1], next(a for a in args if a.startswith('--user='))) for args, _ in calls[1:-1]] == [
        ('t0-seed0', '--user=3000:3000'), ('t0-campaign', '--user=3008:3008')]
    assert all(not any(a.startswith(('--cap-add', '--privileged', '--mount', '--volume')) for a in args) for args, _ in calls)
    assert 'chown' not in SETUP_PROGRAM and 'chown' not in RUNTIME_SETUP_PROGRAM
    assert p == before


def test_all_runtime_directories_are_separate_and_created_before_sealing():
    p = plan()
    second = deepcopy(p['targets'][0]); second['name'] = 'second'; p['targets'].append(second)
    for t in p['targets']: t['corpus'] = ['a', 'b', 'c']
    transport = SetupTransport(); prepare_workspace(transport, 'owned-container', p)
    phases = [a for a, _ in transport.calls if RUNTIME_SETUP_PROGRAM in a]
    users = [next(s for s in a if s.startswith('--user=')) for a in phases]
    assert len(phases) == len(set(users)) == 8
    assert {a[-1] for a in phases} == {
        't0-seed0', 't0-seed1', 't0-seed2', 't0-campaign',
        't1-seed0', 't1-seed1', 't1-seed2', 't1-campaign'}


@pytest.mark.parametrize('altered', ['root', 'seal', 'uid', 'gid', 'name'])
def test_unverified_directory_setup_never_becomes_successful( altered):
    with pytest.raises(ValueError, match='worker_fuzz_setup_unverified'):
        prepare_workspace(SetupTransport(altered=altered), 'owned-container', plan())


def test_interruption_stops_setup_without_running_project_commands():
    calls = []
    def transport(args, **kwargs):
        calls.append(args)
        raise ValueError('worker_local_lease_expired')
    with pytest.raises(ValueError, match='worker_local_lease_expired'):
        prepare_workspace(transport, 'owned-container', plan())
    assert len(calls) == 1 and SETUP_PROGRAM in calls[0]


def test_setup_programs_are_self_contained_syntax_validated():
    for program in (SETUP_PROGRAM, RUNTIME_SETUP_PROGRAM, SEAL_SETUP_PROGRAM):
        compile(program, '<fuzz-setup>', 'exec')
    assert 'stat.S_IMODE(info.st_mode) != 0o1777' in RUNTIME_SETUP_PROGRAM
    assert 'root.chmod(0o555)' in SEAL_SETUP_PROGRAM
