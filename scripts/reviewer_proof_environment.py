"""Owned synthetic build/server environment; no ambient backend or credential config."""
import os
from pathlib import Path
import subprocess
import tempfile
from reviewer_proof_diagnostics import run_with_diagnostics, set_stage


def environment(root, mode):
    assert mode in {'build','server'}
    web=root/'apps/web'
    for name in ('.env','.env.local','.env.production','.env.production.local'):
        if (web/name).exists():
            raise RuntimeError('dotenv input prohibited in synthetic proof')
    env={k:os.environ[k] for k in ('PATH','LANG','LC_ALL','TMPDIR') if k in os.environ}
    env.update(NEXT_TELEMETRY_DISABLED='1', NODE_ENV='production',
               NICO_REVIEWER_PROOF_NETWORK=mode,
               NODE_OPTIONS='--require='+str(root/'scripts/reviewer_proof_node_guard.cjs'))
    return env


def build(root):
    set_stage('environment')
    env=environment(root,'build')
    # Registry acquisition only; no lifecycle scripts, cache credentials or ambient npm config.
    install={k:v for k,v in env.items() if k not in ('NODE_OPTIONS','NICO_REVIEWER_PROOF_NETWORK','NODE_ENV')}
    # npm rejects loading the same path as both user and global configuration.
    # Keep distinct empty files alive through both subprocesses, then remove them.
    with tempfile.TemporaryDirectory(prefix='nico-reviewer-npm-') as directory:
        configs = {'NPM_CONFIG_USERCONFIG': Path(directory)/'user.npmrc',
                   'NPM_CONFIG_GLOBALCONFIG': Path(directory)/'global.npmrc'}
        for path in configs.values():
            path.write_bytes(b'')
        config_env = {key: str(path) for key, path in configs.items()}
        install.update(config_env)
        env.update(config_env)
        set_stage('npm-install')
        subprocess.run(['npm','ci','--ignore-scripts','--no-audit','--no-fund'],cwd=root/'apps/web',env=install,check=True,timeout=240)
        set_stage('frontend-build')
        subprocess.run(['node','node_modules/next/dist/bin/next','build'],cwd=root/'apps/web',env=env,check=True,timeout=240)

if __name__=='__main__':
    root = Path(__file__).resolve().parents[1]
    run_with_diagnostics(root, 'build', lambda: build(root))
