from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/prepare_playwright_webkit_native_visibility_v1.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "nico_playwright_webkit_native_visibility_preparation_test_subject",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_prepare_is_exact_idempotent_and_preserves_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preparation = _load()
    original = b"prefix exact WebKit override suffix"
    patched = b"prefix guarded WebKit override suffix"
    monkeypatch.setattr(preparation, "ORIGINAL", "exact WebKit override")
    monkeypatch.setattr(preparation, "PATCHED", "guarded WebKit override")
    monkeypatch.setattr(preparation, "ORIGINAL_SHA256", _sha256(original))
    monkeypatch.setattr(preparation, "PATCHED_SHA256", _sha256(patched))
    bundle = tmp_path / "coreBundle.js"
    bundle.write_bytes(original)
    bundle.chmod(0o640)

    assert preparation.prepare(bundle) == _sha256(patched)
    assert bundle.read_bytes() == patched
    assert bundle.stat().st_mode & 0o777 == 0o640
    assert preparation.prepare(bundle) == _sha256(patched)


def test_prepare_fails_closed_for_unknown_bundle(tmp_path: Path) -> None:
    preparation = _load()
    bundle = tmp_path / "coreBundle.js"
    bundle.write_bytes(b"unknown Playwright bundle")

    with pytest.raises(
        RuntimeError,
        match="playwright_webkit_native_visibility_bundle_hash_mismatch",
    ):
        preparation.prepare(bundle)

    assert bundle.read_bytes() == b"unknown Playwright bundle"


def test_preparation_contract_pins_one_version_and_exact_hashes() -> None:
    preparation = _load()

    assert preparation.PLAYWRIGHT_VERSION == "1.61.0"
    assert preparation.RUNTIME_VERSION == "nico.playwright_webkit_native_visibility.v1"
    assert preparation.ORIGINAL_SHA256 == (
        "6be5c2ea035554e9b184b1dbc7aa5e7f1fb428dd1b5c202022858dcfae9bee27"
    )
    assert preparation.PATCHED_SHA256 == (
        "f59c337b321f0172eb26e2c721e04852f2495d41b2da4b8bcdf99de501b9e083"
    )
