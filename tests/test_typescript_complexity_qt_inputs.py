from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from nico import typescript_ast_complexity_v1 as complexity
from nico.node_scanner_applicability_v1 import _qt_translation

FIXTURE = Path(__file__).parent / "fixtures" / "bitcoin_qt_translation" / "bitcoin_sq.ts"
QT_PATH = "src/qt/locale/bitcoin_sq.ts"
CONTROL_PATH = "src/control.ts"
CONTROL = "export function control(value: number): number { return value > 0 ? 1 : 0; }"


def _real_inputs():
    raw = FIXTURE.read_bytes()
    assert len(raw) == 27579
    assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == "4aa7611b9bdeb174607810572d0ac79720edad14"
    assert _qt_translation(FIXTURE, QT_PATH) is not None
    return {QT_PATH: raw.decode("utf-8"), CONTROL_PATH: CONTROL}


@pytest.mark.parametrize("parser_mode", ["unavailable", "automatic"])
def test_real_bitcoin_qt_xml_is_not_typescript_complexity(monkeypatch, parser_mode):
    if parser_mode == "unavailable":
        monkeypatch.setattr(complexity, "_run_typescript_ast",
                            lambda files: {"status": "unavailable", "analyses": []})
    result = complexity._build_complexity(_real_inputs())
    assert result["files_considered"] == 1
    assert result["files_analyzed"] == 1
    assert result["javascript_typescript_files_analyzed"] == 1
    assert result["analyzed_source_paths"] == [CONTROL_PATH]
    assert result["source_coverage_percent"] == 100.0
    assert result["source_candidates_before_format_filter"] == 2
    assert result["qt_translation_files_excluded"] == 1
    assert result["qt_translation_paths_excluded"] == [QT_PATH]
    assert result["format_filter_scope"] == "supported_qt_xml_in_utf8_text"

@pytest.mark.parametrize("content", [
    CONTROL,
    "<TS version='2.1'><context><name>Wallet</name><message><source>Open</source></message>",
    "<TS version='2.1'><context><name>Wallet</name><message><source>Open</source><unknown/></message></context></TS>",
    "<!DOCTYPE TS [<!ENTITY injected 'value'>]><TS version='2.1'><context><name>Wallet</name><message><source>&injected;</source></message></context></TS>",
    "<TS version='2.1'><context><name>Wallet</name><message><source>\ufffd</source></message></context></TS>",
    "<?xml version='1.0' encoding='ISO-8859-1'?><TS version='2.1'><context><name>Wallet</name><message><source>Open</source></message></context></TS>",
    "\ud800",
])
def test_unsupported_or_lossy_text_never_establishes_noncode(monkeypatch, content):
    monkeypatch.setattr(complexity, "_run_typescript_ast",
                        lambda files: {"status": "unavailable", "analyses": []})
    result = complexity._build_complexity({"src/ambiguous.ts": content})
    assert result["files_considered"] == 1
    assert result["javascript_typescript_files_analyzed"] == 1
    assert result["analyzed_source_paths"] == ["src/ambiguous.ts"]
    assert result["qt_translation_files_excluded"] == 0
    assert result["source_candidates_before_format_filter"] == 1


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "utf-16-be"])
def test_factored_byte_recognition_preserves_original_identity(tmp_path, encoding):
    from nico.node_scanner_applicability_v1 import is_supported_qt_translation_bytes

    text = "<TS version='2.1'><context><name>Wallet</name><message><source>Open</source><translation>Abrir</translation></message></context></TS>"
    raw = text.encode(encoding)
    if encoding == "utf-16-be":
        raw = b"\xfe\xff" + raw
    path = tmp_path / "translation.ts"
    path.write_bytes(raw)
    assert is_supported_qt_translation_bytes(raw) is True
    record = _qt_translation(path, "translation.ts")
    assert record == {"path": "translation.ts", "format": "qt-ts-xml-v1",
                      "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
    assert path.read_bytes() == raw


def test_replacement_decoded_utf16_is_not_claimed_as_lossless_utf8():
    raw = "<TS version='2.1'><context><name>Wallet</name><message><source>Open</source></message></context></TS>".encode("utf-16")
    assert not complexity._supported_qt_source_text("translation.ts", raw.decode("utf-8", errors="replace"))


def test_qt_only_population_does_not_claim_code_execution():
    result = complexity._build_complexity({QT_PATH: _real_inputs()[QT_PATH]})
    assert result["status"] == "unavailable"
    assert result["files_considered"] == result["files_analyzed"] == 0
    assert result["javascript_typescript_files_analyzed"] == 0
    assert result["source_coverage_percent"] == 0.0
    assert result["source_candidates_before_format_filter"] == 1
    assert result["qt_translation_paths_excluded"] == [QT_PATH]
    assert result["source_parse_limitations"] == 0


def test_acquisition_population_and_original_raw_hashes_remain_intact():
    import io
    import zipfile

    from nico.full_source_archive_profile_v1 import _archive_sources

    expected = {QT_PATH: FIXTURE.read_bytes(), CONTROL_PATH: CONTROL.encode()}
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        for path, raw in expected.items():
            output.writestr("bitcoin-frozen/" + path, raw)
    files, metadata = _archive_sources(archive.getvalue())
    before = dict(files)
    result = complexity._build_complexity(files)
    assert files == before
    assert metadata["source_inventory_paths"] == sorted(expected)
    assert metadata["source_files_loaded"] == metadata["source_files_inspected"] == 2
    assert metadata["source_bytes_loaded"] == sum(map(len, expected.values()))
    for path, raw in expected.items():
        record = metadata["source_raw_input_records"][path]
        assert record["sha256"] == hashlib.sha256(raw).hexdigest()
        assert record["bytes"] == len(raw)
        assert record["blob_sha"] == hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    assert result["files_analyzed"] == 1


@pytest.mark.parametrize("count,status,expected_count", [
    (3, "analyzed_with_diagnostics", "3"),
    (None, "analyzed_with_diagnostics", "unreported"),
    (2, "analyzed", "2"),
])
def test_ast_diagnostics_are_explicit_partial_observations(monkeypatch, count, status, expected_count):
    analysis = {"path": CONTROL_PATH, "language": "javascript-typescript",
                "method": "typescript_compiler_ast", "status": status,
                "parser_diagnostic_count": count, "functions": [], "source_loc": 1}
    monkeypatch.setattr(complexity, "_run_typescript_ast",
                        lambda files: {"status": "complete", "analyses": [analysis]})
    result = complexity._build_complexity({CONTROL_PATH: CONTROL})
    assert result["files_analyzed"] == result["typescript_ast_files_analyzed"] == 1
    assert result["source_parse_limitations"] == 1
    assert result["parse_notes"] == [
        f"TypeScript AST parsed {CONTROL_PATH} with {expected_count} diagnostics; numeric observations are partial."
    ]
    assert any("parser limitation" in note.lower() for note in result["unavailable_data_notes"])


def test_real_typescript_parser_diagnostics_survive_collection():
    path = "src/broken.ts"
    files = {path: "export function broken( {"}
    raw = complexity._run_typescript_ast(files)
    assert raw["status"] == "complete"
    assert raw["analyses"][0]["parser_diagnostic_count"] > 0
    result = complexity._build_complexity(files)
    assert result["files_considered"] == result["files_analyzed"] == 1
    assert result["typescript_ast_files_analyzed"] == 1
    assert result["qt_translation_files_excluded"] == 0
    assert result["source_parse_limitations"] == 1
    assert any(path in note and "partial" in note for note in result["parse_notes"])


def test_omitted_ast_file_keeps_distinct_missing_evidence_note(monkeypatch):
    monkeypatch.setattr(complexity, "_run_typescript_ast",
                        lambda files: {"status": "complete", "analyses": []})
    result = complexity._build_complexity({CONTROL_PATH: CONTROL})
    assert result["files_considered"] == 1
    assert result["files_analyzed"] == 0
    assert result["source_parse_limitations"] == 1
    assert result["parse_notes"] == [
        f"TypeScript AST output omitted {CONTROL_PATH}; no lexical substitute was used for that file."
    ]

def test_scope_and_partial_parser_notes_have_strict_spanish_parity():
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation_field

    result = complexity._build_complexity(_real_inputs())
    translated = _translate_presentation_field(result["scope"], "evidence")
    assert "XML de Qt" in translated and "UTF-8" in translated
    old_scope = "Exact-SHA first-party source archive when available; tests, generated, distribution, dependency, vendor, and minified paths are excluded."
    assert "XML de Qt" not in _translate_presentation_field(old_scope, "evidence")
    for count in ("3", "unreported"):
        note = f"TypeScript AST parsed {CONTROL_PATH} with {count} diagnostics; numeric observations are partial."
        translated = _translate_presentation_field(note, "evidence")
        assert CONTROL_PATH in translated and "son parciales" in translated
        with pytest.raises(ValueError):
            _translate_presentation_field(note + " Invented successful scanner execution.", "evidence")


@pytest.mark.parametrize("raw", [
    b"",
    b"\xff\xfe\x00\x00<\x00\x00\x00T\x00\x00\x00S\x00\x00\x00",
    b"<?unexpected instruction?><TS version='2.1'><context><name>X</name><message><source>X</source></message></context></TS>",
    b"<!DOCTYPE TS SYSTEM 'https://invalid.example/entity'><TS version='2.1'><context><name>X</name><message><source>X</source></message></context></TS>",
    b"<TS version='2.1'><context><name>X</name><message><source>X</source><unknown/></message></context></TS>",
])
def test_factored_byte_predicate_keeps_encoding_schema_and_entity_rejections(raw):
    from nico.node_scanner_applicability_v1 import is_supported_qt_translation_bytes

    assert is_supported_qt_translation_bytes(raw) is False


def test_factored_byte_predicate_keeps_existing_size_limit():
    from nico.node_scanner_applicability_v1 import MAX_QT_TRANSLATION_BYTES, is_supported_qt_translation_bytes

    assert is_supported_qt_translation_bytes(b" " * (MAX_QT_TRANSLATION_BYTES + 1)) is False
