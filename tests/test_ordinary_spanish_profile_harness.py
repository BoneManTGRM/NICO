import cProfile
from copy import deepcopy
import subprocess
import sys
import time
import pytest

from scripts.profile_ordinary_spanish_render import summarize


def test_profile_counts_recursive_copy_without_recording_values():
    source = {'private_fixture_marker': [[1, 2], [3, 4]]}
    profiler = cProfile.Profile(timer=time.process_time_ns, timeunit=1e-9)
    profiler.runcall(deepcopy, source)
    result = summarize(profiler)
    assert result['categories']['copying']['recursive_calls'] > 0
    assert result['categories']['copying']['self_cpu_seconds'] >= 0
    assert 'private_fixture_marker' not in str(result)


def test_wall_timeout_does_not_claim_success_or_leave_output(tmp_path):
    output = tmp_path / 'profile.json'
    result = subprocess.run(
        [sys.executable, '-m', 'scripts.profile_ordinary_spanish_render',
         '--output', str(output), '--wall-seconds', '1', '--cpu-seconds', '100'],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode != 0
    assert 'wall-time bound' in result.stderr
    assert not output.exists()


@pytest.mark.parametrize('mode', ([], ['--worker']))
def test_existing_profile_is_not_overwritten(tmp_path, mode):
    output = tmp_path / 'profile.json'
    output.write_text('prior evidence')
    result = subprocess.run(
        [sys.executable, '-m', 'scripts.profile_ordinary_spanish_render', '--output', str(output), *mode],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0
    assert output.read_text() == 'prior evidence'


def test_cpu_limit_stops_worker_without_success_output(tmp_path):
    output = tmp_path / 'profile.json'
    result = subprocess.run(
        [sys.executable, '-m', 'scripts.profile_ordinary_spanish_render',
         '--output', str(output), '--wall-seconds', '15', '--cpu-seconds', '1'],
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode != 0
    assert 'CPU bound' in result.stderr
    assert not output.exists()
