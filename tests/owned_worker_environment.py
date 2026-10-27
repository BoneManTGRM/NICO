"""Pure environment construction for owned offline renderer subprocesses."""
from pathlib import Path
from typing import Mapping
import os


def owned_worker_environment(root: Path, temporary_root: Path, parent: Mapping[str, str]) -> dict[str, str]:
    """Never forward ambient service/storage credentials or backend configuration."""
    environment = {key: parent[key] for key in ('PATH', 'LANG', 'PYTHONPATH') if key in parent}
    environment.update({
        'PYTHONPATH': str(root) + os.pathsep + environment.get('PYTHONPATH', ''),
        'PYTHONNOUSERSITE': '1',
        'NICO_HOME': str(temporary_root),
        'NICO_SQLITE_PATH': str(temporary_root / 'nico.sqlite3'),
    })
    return environment
