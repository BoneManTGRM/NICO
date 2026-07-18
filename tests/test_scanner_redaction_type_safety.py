from __future__ import annotations

from nico.scanner_redaction_type_safety import _coerce_text


def test_bytes_are_decoded_before_regex_redaction() -> None:
    assert _coerce_text(b"hello") == "hello"


def test_none_and_scalars_are_normalized() -> None:
    assert _coerce_text(None) == ""
    assert _coerce_text(404) == "404"
    assert _coerce_text(True) == "True"


def test_structured_values_are_serialized_deterministically() -> None:
    result = _coerce_text({"b": 2, "a": "x"})
    assert result == '{"a": "x", "b": 2}'


def test_wrapper_installs_before_express_report_recovery() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "nico" / "express_report_generation_recovery.py").read_text(encoding="utf-8")
    assert "install_scanner_redaction_type_safety" in source
    assert "scanner_normalization = install_scanner_redaction_type_safety()" in source
    assert '"scanner_output_normalization": scanner_normalization' in source
