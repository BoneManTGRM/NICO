"""Full bilingual rendering through production admission using synthetic inputs.

Historical pre-admission qualification is preserved in its immutable archive.
No rendering, integrity, approval, delivery or language gate is overridden here.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from copy import deepcopy

import pytest

from tests.test_cross_locale_pdf_repeatability_v1 import (
    _fixed_status,
    _pdf_observation,
    locale_report,
)


def _offline_observation(status, language):
    return _pdf_observation(status, language)


def _fresh_offline_observation(status, language, seed):
    code = (
        "import json,sys;"
        "from tests.test_spanish_render_qualification_v1 import _offline_observation;"
        "status,language=json.load(sys.stdin);"
        "print('NICO_RENDER_QUALIFICATION='+json.dumps(_offline_observation(status,language),sort_keys=True))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], input=json.dumps([status, language]),
        text=True, capture_output=True, timeout=180, check=False,
        env={**{key: os.environ[key] for key in ("PATH", "LANG", "PYTHONPATH") if key in os.environ},
             "PYTHONHASHSEED": seed},
    )
    assert result.returncode == 0, result.stderr
    observations = [line.removeprefix("NICO_RENDER_QUALIFICATION=")
                    for line in result.stdout.splitlines()
                    if line.startswith("NICO_RENDER_QUALIFICATION=")]
    assert len(observations) == 1
    return json.loads(observations[0])


@pytest.mark.parametrize("source_language,target_language", [("en", "es-MX"), ("es-MX", "en")])
@pytest.mark.parametrize("mode", ["warm", "fresh_process"])
def test_real_spanish_pdf_repeatability_without_admission_short_circuit(mode, source_language, target_language, record_property):
    started = time.monotonic()
    status = _fixed_status(source_language)
    original = deepcopy(status)
    english_before = _pdf_observation(status, source_language)
    if mode == "warm":
        first = _offline_observation(status, target_language)
        _pdf_observation(status, source_language)
        time.sleep(1.05)
        second = _offline_observation(status, target_language)
    else:
        first = _fresh_offline_observation(status, target_language, "0")
        time.sleep(1.05)
        second = _fresh_offline_observation(status, target_language, "1")
    english_after = _pdf_observation(status, source_language)
    assert status == original
    assert first == second, {"first": first, "second": second}
    assert first["pages"] > 0 and first["bytes"] > 0
    assert first["report_language"] == target_language
    assert first["canonical_truth_sha256"] == english_before["canonical_truth_sha256"]
    assert english_before == english_after
    locale_report.require_new_report_language("es-MX")
    with pytest.raises(ValueError, match="^unsupported_report_language$"):
        locale_report.require_new_report_language("fr")
    record_property("qualification_wall_seconds", round(time.monotonic() - started, 3))
    record_property("target_pdf_sha256", first["pdf_sha256"])
    record_property("source_pdf_sha256", english_before["pdf_sha256"])
    record_property("target_pages", first["pages"])


def test_fresh_full_worker_phase17_bilingual_repeatability(tmp_path, record_property):
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    environment = {key: os.environ[key] for key in ("PATH", "LANG", "PYTHONPATH") if key in os.environ}
    environment.update({
        "PYTHONPATH": str(root) + os.pathsep + environment.get("PYTHONPATH", ""),
        "NICO_HOME": str(tmp_path), "NICO_SQLITE_PATH": str(tmp_path / "nico.sqlite3"),
        "RAILWAY_GIT_COMMIT_SHA": "a" * 40, "NICO_RELEASE_COMMIT_SHA": "a" * 40,
        "NICO_FRONTEND_BUILD_COMMIT_SHA": "b" * 40,
        "RAILWAY_DEPLOYMENT_ID": "synthetic-worker-qualification",
        "PYTHONHASHSEED": "0",
    })
    result = subprocess.run(
        [sys.executable, str(root / "tests/spanish_worker_qualification_probe.py")],
        cwd=root, env=environment, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    lines = [line.removeprefix("NICO_WORKER_QUALIFICATION=") for line in result.stdout.splitlines()
             if line.startswith("NICO_WORKER_QUALIFICATION=")]
    assert len(lines) == 1
    observation = json.loads(lines[0])
    assert set(observation) == {"en", "es-MX"}
    record_property("full_worker_observation", json.dumps(observation, sort_keys=True))
