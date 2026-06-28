from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NICO_HOME = Path(os.getenv('NICO_HOME', PROJECT_ROOT / '.nico'))
DB_PATH = Path(os.getenv('NICO_DB_PATH', NICO_HOME / 'nico.sqlite3'))
REPORT_DIR = Path(os.getenv('NICO_REPORT_DIR', NICO_HOME / 'reports'))
TEST_LAB = PROJECT_ROOT / 'nico' / 'test_lab'
SAMPLE_REPO = TEST_LAB / 'sample_repo'
DRIFT_REPO = TEST_LAB / 'drift_workspace'
