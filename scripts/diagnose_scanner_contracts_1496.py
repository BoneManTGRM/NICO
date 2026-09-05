"""Bounded diagnostic evidence, not a production or all-scanner clearance."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.request import Request, urlopen


def main() -> int:
    output = Path('audit-results'); output.mkdir(exist_ok=True)
    observations = []
    def persist():
        (output / 'diagnostics.json').write_text(json.dumps({'schema':'nico.scanner-command-diagnostics.v2', 'production_clearance':False,'observations':observations}, indent=2))
    def command(args, cwd):
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=120, check=False)
        observations.append({'args': list(args), 'returncode': result.returncode, 'stdout': result.stdout[:16000], 'stderr': result.stderr[:16000]})
        persist()
        return result
    # Read public inventory only. No operator credential or production mutation.
    try:
        url = 'https://nico-production-690a.up.railway.app/diagnostics/hosted-scanner-runtime'
        with urlopen(Request(url, headers={'Accept':'application/json','Cache-Control':'no-cache'}), timeout=150) as response:
            inventory = json.load(response)
        observations.append({'deployed_runtime_inventory': {
            'generated_at': inventory.get('generated_at'),
            'runtime': inventory.get('runtime'),
            'config': inventory.get('config'),
            'tools': [{key: item.get(key) for key in ('tool','path','installed','status','version','returncode')} for item in inventory.get('tools', [])],
        }})
    except Exception as exc:
        observations.append({'deployed_inventory_error':type(exc).__name__})
    persist()
    from nico.api.specialist_ship_ready_bootstrap import app
    from nico import scanner_tool_runners
    from nico.worker_execution import WorkerWorkspace
    def active_scan(workspace, label):
        for name in ('trufflehog', 'osv-scanner'):
            spec = next(s for s in scanner_tool_runners.TOOL_SPECS if s.name == name)
            try:
                # No injected runner: production uses this exact default binding.
                result = scanner_tool_runners.run_scanner_tool(spec, workspace)
                allowed = ('tool','status','scanner_tool_version','returncode','exit_code','reason','failure_or_unavailable_reason','stderr','command_intent','output_capture_complete','raw_artifact_retention_complete','full_history_verified','history_scope','commit_sha','raw_artifact','artifact_hash')
                observations.append({'active_default_scanner':name,'fixture':label,'payload':{k:result.get(k) for k in allowed}})
            except Exception as exc:
                observations.append({'active_default_scanner':name,'fixture':label,'exception':type(exc).__name__,'message':str(exc)[:1000]})
            persist()
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
            (osv, '--version'),
            (osv, 'scan', 'source', '--help'),
            (osv, 'scan', 'source', '-r', '.', '--format', 'json'),
            (osv, 'scan', 'source', '-r', '--format', 'json', '--no-call-analysis=all', '.'),
        ]:
            command(args, repo)
        active_scan(WorkerWorkspace(root=root), 'synthetic-local-dependency')
    # Reproduce the same public source revision that produced incomplete reports.
    # Only clone and static-analysis operations; do not run repository scripts.
    with tempfile.TemporaryDirectory(prefix='nico-gitlab-contract-') as temporary:
        root = Path(temporary); repo = root / 'repo'; repo.mkdir()
        sha = 'ddd0f15ae83993f5cb66a927a28673882e99100b'
        for args in [('git','init','-q'), ('git','fetch','--no-tags','https://gitlab.com/gitlab-org/gitlab-test.git',sha), ('git','checkout','--detach',sha)]:
            result = command(args, repo)
            if result.returncode != 0:
                raise RuntimeError('public exact-source fixture checkout failed')
        actual = command(('git','rev-parse','HEAD'),repo).stdout.strip()
        if actual != sha:
            raise RuntimeError('public fixture source mismatch')
        active_scan(WorkerWorkspace(root=root), 'public-gitlab-exact-failing-revision')
    persist()
    print('Retained actual runtime inventory and default-runner diagnostics; no clearance asserted.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
