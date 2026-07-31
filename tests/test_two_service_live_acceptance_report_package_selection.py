from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "two_service_live_acceptance_v3_impl.py"


def _module():
    module_name = "two_service_live_acceptance_v3_impl_report_package_test"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def _canonical_package(truth_hash: str = "a" * 64) -> dict[str, object]:
    return {
        "service_id": "comprehensive",
        "canonical_truth_sha256": truth_hash,
        "json": {
            "canonical_truth_sha256": truth_hash,
            "assessment": {"sections": []},
        },
    }


def _compatibility_shell(truth_hash: str = "a" * 64) -> dict[str, object]:
    return {
        "service_id": "comprehensive",
        "canonical_truth_sha256": truth_hash,
        "markdown": "# NICO Comprehensive Technical Assessment",
        "html": "<!doctype html><html><body>NICO</body></html>",
        "pdf_base64": "JVBERi0xLjQK",
    }


def test_comprehensive_report_selection_preserves_canonical_json_and_compatibility_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    canonical = _canonical_package()
    shell = _compatibility_shell()
    monkeypatch.setattr(module, "_original_report_package", lambda *_args: canonical)

    selected = module._report_package("comprehensive", {"reports": shell})

    assert selected["json"] == canonical["json"]
    assert selected["markdown"] == shell["markdown"]
    assert selected["html"] == shell["html"]
    assert selected["pdf_base64"] == shell["pdf_base64"]
    assert selected["canonical_truth_sha256"] == "a" * 64


def test_comprehensive_report_selection_keeps_compatibility_shell_when_no_canonical_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    shell = _compatibility_shell()
    monkeypatch.setattr(module, "_original_report_package", lambda *_args: {})

    assert module._report_package("comprehensive", {"reports": shell}) == shell


def test_comprehensive_report_selection_fails_closed_on_truth_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    monkeypatch.setattr(
        module,
        "_original_report_package",
        lambda *_args: _canonical_package("a" * 64),
    )

    with pytest.raises(AssertionError, match="canonical truth hash drift"):
        module._report_package(
            "comprehensive",
            {"reports": _compatibility_shell("b" * 64)},
        )
