from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_bandit_reliably.py"
    spec = importlib.util.spec_from_file_location("run_bandit_reliably", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runner_module_loads() -> None:
    module = load_module()
    assert callable(module.main)
    assert callable(module.sha256_file)


def test_sha256_file_is_stable(tmp_path: Path) -> None:
    module = load_module()
    artifact = tmp_path / "artifact.json"
    artifact.write_text('{"results": []}', encoding="utf-8")
    first = module.sha256_file(artifact)
    second = module.sha256_file(artifact)
    assert first == second
    assert len(first) == 64
