from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_builder():
    path = ROOT / "scripts" / "build_phase6_verification_package.py"
    spec = importlib.util.spec_from_file_location("phase6_verification_builder", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verification_builder_uses_innermost_repository_root() -> None:
    module = _load_builder()
    assert module._repository_path("/home/runner/work/NICO/NICO/nico/comprehensive_run_store.py") == "nico/comprehensive_run_store.py"
    assert module._repository_path("C:/work/NICO/apps/web/app/page.tsx") == "apps/web/app/page.tsx"


def test_scanner_authority_order_matches_phase6_contract() -> None:
    source = (ROOT / "nico" / "phase6_final_remediation_v1.py").read_text(encoding="utf-8")
    block = source.split("items.sort(", 1)[1].split("reverse=True", 1)[0]
    tokens = [
        "exact_commit_match",
        "raw_artifact_retention_complete",
        "verified_artifact_hash",
        "execution_complete",
        "observed_at",
    ]
    positions = [block.index(token) for token in tokens]
    assert positions == sorted(positions)
    assert "current_run" not in block
