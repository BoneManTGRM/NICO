"""Image wiring and fail-closed owned cross-compiler link controls."""
from pathlib import Path
import subprocess

import pytest
import yaml

from scripts import verify_cpp_runtime_toolchain as control


def test_full_project_image_selects_gcc14_and_checks_real_capnp_before_use():
    image = Path('docker/assessment-full-project-fuzz.Dockerfile').read_text()
    assert "printf '%s\\n' '--gcc-toolchain=/usr/local'" in image
    assert '/usr/lib/llvm-17/bin/clang.cfg' in image
    assert '/usr/lib/llvm-17/bin/clang++.cfg' in image
    assert 'timeout 30s python3 /opt/verify_cpp_runtime_toolchain.py' in image
    assert image.index('COPY --from=capnp-builder') < image.index('timeout 30s python3') < image.index('USER 1000:1000')
    workflow = yaml.safe_load(Path('.github/workflows/cpp-full-project-integration.yml').read_text())
    builds = [s['run'] for j in workflow['jobs'].values() for s in j['steps']
              if 'docker/assessment-full-project-fuzz.Dockerfile' in s.get('run', '')]
    assert len(builds) == 2
    assert all('cp scripts/verify_cpp_runtime_toolchain.py toolchain/full-project/' in b for b in builds)
    assert all('cpp-runtime-toolchain.json' in b for b in builds)


@pytest.mark.parametrize('failure', ['command', 'timeout', 'missing', 'version'])
def test_failed_or_missing_controls_cannot_claim_toolchain_success(failure):
    def run(argv, **kwargs):
        assert kwargs['timeout'] <= 20 and kwargs['check'] is False
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(argv, 20)
        if failure == 'missing':
            raise FileNotFoundError('owned compiler missing')
        return subprocess.CompletedProcess(argv, 1 if failure == 'command' else 0,
                                           stdout='wrong version', stderr='failed')
    result = control.verify(run=run)
    assert result['status'] == 'UNPROVEN' and result['error']
    assert result['assessed_source_executed'] is False
    assert result['native_qualification_completed'] is False


def test_full_image_supports_standalone_worker_interpreter_as_runtime_user():
    """The image build runs the launcher's exact interpreter mode as uid 1000."""
    import shlex
    image = Path('docker/assessment-full-project-fuzz.Dockerfile').read_text()
    launcher = Path('nico/assessment_worker_container.py').read_text()
    link = 'ln -s /usr/bin/python3 /usr/local/bin/python'
    preflight = next(line.removeprefix('RUN ') for line in image.splitlines()
                     if line.startswith('RUN python -I -S '))
    argv = shlex.split(preflight)
    assert argv[:4] == ['python', '-I', '-S', '-c']
    assert '"--entrypoint=python", image, "-I", "-S", "-c", PROGRAM' in launcher
    assert image.index(link) < image.index('USER 1000:1000') < image.index('RUN ' + preflight)
    assert 'sys.flags.isolated and sys.flags.no_site' in argv[4]
    assert '(os.getuid(), os.getgid()) == (1000, 1000)' in argv[4]
    compile(argv[4], '<image-runtime-interpreter-preflight>', 'exec')


def test_pr_full_image_runs_release_standalone_control_before_project_controls():
    workflow = yaml.safe_load(Path('.github/workflows/cpp-full-project-integration.yml').read_text())
    steps = workflow['jobs']['owned-project-integration']['steps']
    runs = [step.get('run', '') for step in steps]
    control = 'python -m scripts.qualify_cppcheck_worker_control --image "$(cat full-project-image-id.txt)"'
    index = runs.index(control)
    assert index < next(i for i, run in enumerate(runs) if 'scripts.qualify_cpp_full_project_integration' in run)
    assert steps[index].get('continue-on-error', False) is False
    assert 'if' not in steps[index]
