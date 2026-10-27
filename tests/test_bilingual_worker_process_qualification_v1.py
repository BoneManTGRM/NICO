"""Offline full-worker repeatability; does not qualify production admission.

Two independently bootstrapped workers render the same owned bilingual fixture.
The invoking interpreter is recorded; Python 3.12 is supplemental to 3.11.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def test_bilingual_worker_artifacts_repeat_across_fresh_hash_seeds(tmp_path, record_property):
    root = Path(__file__).resolve().parents[1]
    snapshots = []
    for seed in ('0', '1'):
        child_root = tmp_path / seed
        child_root.mkdir()
        environment = {key: os.environ[key] for key in ('PATH', 'LANG', 'PYTHONPATH') if key in os.environ}
        environment.update({
            'PYTHONPATH': str(root) + os.pathsep + environment.get('PYTHONPATH', ''),
            'NICO_HOME': str(child_root), 'NICO_SQLITE_PATH': str(child_root / 'nico.sqlite3'),
            'RAILWAY_GIT_COMMIT_SHA': 'a' * 40, 'NICO_RELEASE_COMMIT_SHA': 'a' * 40,
            'NICO_FRONTEND_BUILD_COMMIT_SHA': 'b' * 40,
            'RAILWAY_DEPLOYMENT_ID': 'synthetic-worker-qualification',
            'PYTHONHASHSEED': seed, 'NICO_TEST_WORKER_RICH_FIXTURE': '1',
            'NICO_TEST_WORKER_EXPORT': str(child_root / 'artifacts'),
        })
        result = subprocess.run(
            [sys.executable, str(root / 'tests/spanish_worker_qualification_probe.py')],
            cwd=root, env=environment, capture_output=True, text=True, timeout=180,
        )
        (child_root / 'stdout.log').write_text(result.stdout)
        (child_root / 'stderr.log').write_text(result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
        lines = [line.removeprefix('NICO_WORKER_QUALIFICATION=') for line in result.stdout.splitlines()
                 if line.startswith('NICO_WORKER_QUALIFICATION=')]
        assert len(lines) == 1
        assert set(json.loads(lines[0])) == {'en', 'es-MX'}
        snapshots.append({language: json.loads((child_root / 'artifacts' / (language + '.json')).read_text())
                          for language in ('en', 'es-MX')})
    for language in ('en', 'es-MX'):
        assert snapshots[0][language] == snapshots[1][language], language
    record_property('interpreter', sys.version)
    record_property('worker_hash_seeds', '0,1')
