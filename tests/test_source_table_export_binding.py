from __future__ import annotations

import base64
import hashlib
import io
import json
from copy import deepcopy

import pytest
from reportlab.pdfgen.canvas import Canvas

from nico.source_table_export_binding import (
    capture_source_table_evidence,
    validate_source_table_evidence,
)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _table(rows=49, title="Complete source inventory"):
    return {
        "title": title,
        "columns": ["Source", "Observed value"],
        "rows": [[f"src/file-{index:03}.py", {"number": index, "literal": "México", "seen": True}]
                 for index in range(rows)],
    }


def _canonical(*tables, language="en"):
    return {
        "identity": {"run_id": "comprun_source_table_binding", "commit_sha": "a" * 40,
                     "report_language": language},
        "report_language": language,
        "stage_summaries": [{"stage_id": "architecture_and_complexity", "structured_tables": list(tables)}],
        "report_finality": "automated_draft",
        "approval_status": "pending_human_approval",
        "human_review_required": True,
        "human_review_completed": False,
        "client_delivery_allowed": False,
    }


def _token(table):
    payload = {key: table[key] for key in ("title", "columns", "rows")}
    return f"NICO-TABLE-{_sha(_json(payload).encode('utf-8'))}-{len(table['rows'])}"


def _pdf(lines):
    output = io.BytesIO()
    document = Canvas(output, invariant=True)
    document.setFont("Helvetica", 7)
    y = 760
    for line in lines:
        document.drawString(36, y, line)
        y -= 14
    document.showPage()
    document.save()
    return output.getvalue()


def _bind_export(package, exported):
    text = _json(exported)
    data = text.encode("utf-8")
    package["canonical_json"] = text
    package["canonical_json_sha256"] = _sha(data)
    manifest = {"manifest_id": "source-table-test", "artifacts": [{
        "artifact_type": "canonical_json", "filename": "nico-canonical.json",
        "sha256": _sha(data), "size_bytes": len(data),
    }]}
    _bind_manifest(package, manifest)


def _bind_manifest(package, manifest):
    package["artifact_manifest"] = manifest
    text = _json(manifest)
    package["evidence_manifest_json"] = text
    package["evidence_manifest_sha256"] = _sha(text.encode("utf-8"))


def _package(canonical, *, tokens=None):
    if tokens is None:
        tokens = [_token(table) for stage in canonical["stage_summaries"]
                  for table in stage["structured_tables"] if len(table["rows"]) > 48]
    language = canonical.get("report_language")
    boundary = ("Borrador automatizado; aprobación humana pendiente; entrega al cliente bloqueada."
                if language == "es-MX" else
                "Automated draft; pending human approval; client delivery blocked.")
    pdf = _pdf([boundary, *tokens])
    package = {"json": deepcopy(canonical), "pdf_base64": base64.b64encode(pdf).decode("ascii"),
               "pdf_sha256": _sha(pdf), "human_review_required": True,
               "human_review_completed": False, "client_delivery_allowed": False,
               "approval_status": "pending_human_approval"}
    _bind_export(package, canonical)
    return package


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_complete_export_and_visible_digest_accept_bilingual_display_without_mutation(language):
    canonical = _canonical(_table(), _table(2, "Additional evidence"), language=language)
    original = deepcopy(canonical)
    expected = capture_source_table_evidence(canonical)
    expected_before = deepcopy(expected)
    package = _package(canonical)
    before = deepcopy(package)
    result = validate_source_table_evidence(expected, package)
    assert isinstance(result, dict)
    assert canonical == original
    assert package == before
    assert expected == expected_before
    assert package["human_review_completed"] is False
    assert package["client_delivery_allowed"] is False
    assert package["json"]["approval_status"] == "pending_human_approval"


@pytest.mark.parametrize("count", [0, 1, 48])
def test_legacy_small_tables_do_not_require_export_manifest_or_pdf(count):
    canonical = _canonical(_table(count))
    expected = capture_source_table_evidence(canonical)
    package = {"json": deepcopy(canonical)}
    before = deepcopy(package)
    assert isinstance(validate_source_table_evidence(expected, package), dict)
    assert package == before


def test_even_legacy_small_table_rows_are_compared_to_captured_input():
    canonical = _canonical(_table(2))
    expected = capture_source_table_evidence(canonical)
    changed = deepcopy(canonical)
    changed["stage_summaries"][0]["structured_tables"][0]["rows"].pop()
    with pytest.raises(ValueError):
        validate_source_table_evidence(expected, {"json": changed})


def test_present_small_table_export_cannot_silently_omit_a_source_row():
    canonical = _canonical(_table(2))
    expected = capture_source_table_evidence(canonical)
    package = _package(canonical)
    incomplete = deepcopy(canonical)
    incomplete["stage_summaries"][0]["structured_tables"][0]["rows"].pop()
    _bind_export(package, incomplete)
    with pytest.raises(ValueError):
        validate_source_table_evidence(expected, package)


@pytest.mark.parametrize("field", [
    "canonical_json", "canonical_json_sha256", "artifact_manifest", "evidence_manifest_json",
    "evidence_manifest_sha256", "pdf_base64",
])
def test_large_table_cannot_drop_required_export_or_pdf_boundary(field):
    canonical = _canonical(_table())
    package = _package(canonical)
    del package[field]
    before = deepcopy(package)
    with pytest.raises(ValueError):
        validate_source_table_evidence(capture_source_table_evidence(canonical), package)
    assert package == before


@pytest.mark.parametrize("mutation", ["drop_row", "replace_cell", "type_drift", "drop_table", "change_title", "change_column"])
def test_output_only_recomputed_hashes_cannot_authorize_changed_source_evidence(mutation):
    canonical = _canonical(_table())
    expected = capture_source_table_evidence(canonical)
    altered = deepcopy(canonical)
    table = altered["stage_summaries"][0]["structured_tables"][0]
    if mutation == "drop_row":
        table["rows"].pop()
    elif mutation == "replace_cell":
        table["rows"][-1][1]["literal"] = "replacement"
    elif mutation == "type_drift":
        table["rows"][1][1]["number"] = True  # Python equality alone would conflate 1 and True.
    elif mutation == "drop_table":
        altered["stage_summaries"][0]["structured_tables"] = []
    elif mutation == "change_title":
        table["title"] = "A substituted table"
    else:
        table["columns"][1] = "A substituted column"
    package = _package(altered)  # All output hashes and visible token agree only with altered data.
    before = deepcopy(package)
    with pytest.raises(ValueError):
        validate_source_table_evidence(expected, package)
    assert package == before


@pytest.mark.parametrize("surface", ["json", "canonical_json"])
def test_inline_and_exported_canonical_each_require_all_original_rows(surface):
    canonical = _canonical(_table())
    expected = capture_source_table_evidence(canonical)
    altered = deepcopy(canonical)
    altered["stage_summaries"][0]["structured_tables"][0]["rows"].pop()
    package = _package(canonical)
    if surface == "json":
        package["json"] = altered
    else:
        _bind_export(package, altered)  # Rebind legitimate hashes; contents are still incomplete.
    with pytest.raises(ValueError):
        validate_source_table_evidence(expected, package)


def test_capture_preserves_duplicate_table_instances_and_original_stage_binding():
    repeated = _table()
    canonical = _canonical(repeated, deepcopy(repeated))
    canonical["stage_summaries"].append({"stage_id": "deployment", "structured_tables": [deepcopy(repeated)]})
    expected = capture_source_table_evidence(canonical)
    assert len(expected) == 3
    assert isinstance(validate_source_table_evidence(expected, _package(canonical)), dict)
    for mutation in ("remove_duplicate", "move_stage"):
        altered = deepcopy(canonical)
        if mutation == "remove_duplicate":
            altered["stage_summaries"][0]["structured_tables"].pop()
        else:
            altered["stage_summaries"][1]["stage_id"] = "another-stage"
        with pytest.raises(ValueError):
            validate_source_table_evidence(expected, _package(altered))


@pytest.mark.parametrize("token_kind", ["absent", "wrong_digest", "wrong_count", "count_prefix", "different_table"])
def test_pdf_must_identify_the_exact_summarized_large_table(token_kind):
    table = _table()
    canonical = _canonical(table)
    token = _token(table)
    if token_kind == "absent":
        tokens = []
    elif token_kind == "wrong_digest":
        tokens = [f"NICO-TABLE-{'0' * 64}-49"]
    elif token_kind == "wrong_count":
        tokens = [token.rsplit("-", 1)[0] + "-50"]
    elif token_kind == "count_prefix":
        tokens = [token + "0"]  # Exact count 49 must not match a token for 490 rows.
    else:
        tokens = [_token(_table(49, "A different table"))]
    with pytest.raises(ValueError):
        validate_source_table_evidence(capture_source_table_evidence(canonical), _package(canonical, tokens=tokens))


@pytest.mark.parametrize("field,value", [
    ("sha256", "0" * 64), ("size_bytes", 1), ("size_bytes", True),
])
def test_canonical_entry_digest_and_integer_byte_size_must_match_exact_export(field, value):
    canonical = _canonical(_table())
    package = _package(canonical)
    manifest = deepcopy(package["artifact_manifest"])
    manifest["artifacts"][0][field] = value
    _bind_manifest(package, manifest)
    with pytest.raises(ValueError):
        validate_source_table_evidence(capture_source_table_evidence(canonical), package)


def test_detached_manifest_object_cannot_diverge_from_hash_bound_manifest_bytes():
    canonical = _canonical(_table())
    package = _package(canonical)
    package["artifact_manifest"]["manifest_id"] = "different-manifest"
    with pytest.raises(ValueError):
        validate_source_table_evidence(capture_source_table_evidence(canonical), package)


@pytest.mark.parametrize("field", ["canonical_json_sha256", "evidence_manifest_sha256"])
def test_declared_hash_must_match_retained_serialized_bytes(field):
    canonical = _canonical(_table())
    package = _package(canonical)
    package[field] = "0" * 64
    with pytest.raises(ValueError):
        validate_source_table_evidence(capture_source_table_evidence(canonical), package)


def test_large_table_added_after_capture_is_not_silently_unbound():
    canonical = _canonical(_table(2))
    expected = capture_source_table_evidence(canonical)
    altered = deepcopy(canonical)
    altered["stage_summaries"][0]["structured_tables"].append(_table())
    with pytest.raises(ValueError):
        validate_source_table_evidence(expected, _package(altered))
