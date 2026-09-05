"""Bounded diagnostics on synthetic local source; never a production clearance."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main() -> int:
    output = Path('audit-results'); output.mkdir(exist_ok=True)
    observations = []
    def command(args, cwd):
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=120, check=False)
        observations.append({'args': list(args), 'returncode': result.returncode, 'stdout': result.stdout[:16000], 'stderr': result.stderr[:16000]})
        return result
    with tempfile.TemporaryDirectory(prefix='nico-synthetic-contract-') as temporary:
        root = Path(temporary); repo = root / 'repo'; repo.mkdir()
        for args in [('git', 'init', '-q'), ('git', 'config', 'user.name', 'Synthetic NICO test'), ('git', 'config', 'user.email', 'synthetic@example.invalid')]:
            command(args, repo)
        (repo / 'README.md').write_text('Synthetic local scanner command contract. No client data.\n')
        (repo / 'requirements.txt').write_text('idna==3.10\n')
        command(('git', 'add', '.'), repo)
        command(('git', 'commit', '-qm', 'synthetic scanner fixture'), repo)
        th = shutil.which('trufflehog'); osv = shutil.which('osv-scanner')
        if not th or not osv:
            raise RuntimeError('checksum-verified scanner binaries are required')
        for args in [
            (th, '--version'),
            (th, 'git', '--help'),
            (th, 'git', repo.as_uri(), '--json', '--no-update', '--no-verification', '--branch', 'HEAD'),
            (th, '--json', '--no-update', '--no-verification', 'git', '--branch', 'HEAD', repo.as_uri()),
            (osv, '--version'),
            (osv, 'scan', 'source', '--help'),
            (osv, 'scan', 'source', '-r', '.', '--format', 'json'),
            (osv, 'scan', 'source', '-r', '--format', 'json', '--no-call-analysis=all', '.'),
        ]:
            command(args, repo)
        # Exercise the final deployed bootstrap, not merely an unbound helper.
        from nico.api.specialist_ship_ready_bootstrap import app
        from nico import scanner_tool_runners
        from nico.worker_execution import WorkerWorkspace, run_command
        workspace = WorkerWorkspace(root=root)
        def retained_runner(args, **kwargs):
            value = run_command(args, **kwargs)
            observations.append({'active_worker_args': list(args), 'returncode': value.returncode, 'stdout': value.stdout[:16000], 'stderr': value.stderr[:16000]})
            return value
        for name in ('trufflehog', 'osv-scanner'):
            spec = next(s for s in scanner_tool_runners.TOOL_SPECS if s.name == name)
            result = scanner_tool_runners.run_scanner_tool(spec, workspace, runner=retained_runner)
            observations.append({'active_scanner': name, 'payload': {k:v for k,v in result.items() if k not in {'raw_artifact_blob','raw_artifact_blobs','findings'}}})
    (output / 'diagnostics.json').write_text(json.dumps({'schema':'nico.scanner-command-diagnostics.v1', 'synthetic_only':True,'production_clearance':False,'observations':observations}, indent=2))
    print('Retained synthetic real-binary diagnostics; no production clearance asserted.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
