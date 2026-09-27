from __future__ import annotations

import hashlib
import io
import json
from copy import deepcopy

import pytest
from pypdf import PdfReader
from reportlab.platypus import SimpleDocTemplate

from nico.comprehensive_report_package import _source_markdown, _source_pdf_tables, _source_tables
from nico.comprehensive_source_table_presentation_v1 import (
    MAX_INLINE_SOURCE_TABLE_ROWS,
    source_table_summaries,
    source_table_summary,
)


def _table(count: int = 49) -> dict:
    return {
        "title": "Observed source components",
        "columns": ["Source", "Kind"],
        "rows": [[f"source_{number:03}.py", "source_module"] for number in range(count)],
    }


def _pdf_text(stage: dict, *, spanish: bool = False) -> str:
    output = io.BytesIO()
    SimpleDocTemplate(output, pagesize=(612, 792)).build(
        _source_pdf_tables(stage, spanish=spanish, width=468)
    )
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(output.getvalue())).pages)


@pytest.mark.parametrize("count", [1, 48])
def test_small_structured_tables_keep_every_inline_row(count):
    table = _table(count)
    assert MAX_INLINE_SOURCE_TABLE_ROWS == 48
    assert source_table_summary(table) is None
    text = _pdf_text({"structured_tables": [table]})
    assert all(row[0] in text for row in table["rows"])
    assert "NICO-TABLE-" not in text
    assert "canonical evidence JSON" not in text


@pytest.mark.parametrize("spanish", [False, True])
def test_large_table_pdf_has_bilingual_exact_count_digest_and_disclosure(spanish):
    table = _table()
    stage = {"structured_tables": [table], "source_observation": {"observation_sha256": "a" * 64}}
    original = deepcopy(stage)
    summary = source_table_summary(table)
    text = _pdf_text(stage, spanish=spanish)
    normalized = " ".join(text.split())
    compact = "".join(text.split())
    assert summary["reference_token"] in compact
    assert summary["sha256"] in compact
    assert "a" * 64 in compact
    assert ("Filas completas conservadas: 49" if spanish else "Complete retained rows: 49") in normalized
    assert ("Componentes observados en el código" if spanish else "Observed source components") in normalized
    assert ("JSON de evidencia canónica de esta misma edición" if spanish else "this same edition's canonical evidence JSON") in normalized
    assert ("no establece verificación en ejecución, aprobación humana ni autorización de entrega" if spanish else
            "does not establish runtime verification, human approval or delivery authorization") in normalized
    assert not any(row[0] in text for row in table["rows"])
    assert stage == original
    # The presentation change does not alter full Markdown or retained tables.
    markdown = "\n".join(_source_markdown(stage, spanish=spanish))
    assert all(row[0] in markdown for row in table["rows"])
    assert _source_tables(stage)[0] == table


def test_hash_binds_exact_typed_title_columns_rows_without_metadata_or_coercion():
    table = _table()
    table["rows"][0] = ["á.py", {"integer": 1, "float": 1.0, "truth": True, "null": None}]
    table["metadata"] = "outside documented digest scope"
    original = deepcopy(table)
    summary = source_table_summary(table)
    payload = {key: table[key] for key in ("title", "columns", "rows")}
    expected = hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()
    assert summary["sha256"] == expected
    assert summary["reference_token"] == f"NICO-TABLE-{expected}-49"
    assert summary["digest_scope"] == "exact_title_columns_rows"
    assert summary["full_rows_artifact"] == "canonical_json"
    assert table == original
    summary["columns"].append("changed descriptor")
    assert table == original
    reordered = {"rows": table["rows"], "columns": table["columns"], "title": table["title"], "metadata": "changed"}
    assert source_table_summary(reordered)["sha256"] == expected


@pytest.mark.parametrize("replacement", ["1", 1, 1.0, True, None])
def test_cell_type_changes_are_not_coerced_to_same_digest(replacement):
    table = _table()
    table["rows"][0][1] = replacement
    digest = source_table_summary(table)["sha256"]
    all_digests = set()
    for value in ("1", 1, 1.0, True, None):
        candidate = deepcopy(table)
        candidate["rows"][0][1] = value
        all_digests.add(source_table_summary(candidate)["sha256"])
    assert len(all_digests) == 5 and digest in all_digests


@pytest.mark.parametrize("field", ["title", "columns", "rows"])
def test_title_columns_and_row_order_each_change_commitment(field):
    table = _table()
    changed = deepcopy(table)
    changed[field] = "Changed title" if field == "title" else list(reversed(changed[field]))
    assert source_table_summary(changed)["sha256"] != source_table_summary(table)["sha256"]


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), object(), {1: "non-string key"}])
def test_large_table_digest_rejects_non_json_values(invalid):
    table = _table()
    table["rows"][0][1] = invalid
    with pytest.raises(ValueError):
        source_table_summary(table)


def test_stage_descriptors_preserve_order_and_deduplicate_only_identical_tables():
    first = _table()
    second = _table(50)
    stages = [{"structured_tables": [first]}, {"structured_tables": [deepcopy(first), second]}]
    original = deepcopy(stages)
    summaries = source_table_summaries(stages)
    assert [summary["row_count"] for summary in summaries] == [49, 50]
    assert stages == original


def test_generated_long_coverage_and_limitation_tables_are_not_summarized():
    source = _table()
    unavailable = [f"missing_{number:03}.py" for number in range(49)]
    unanalyzed = [f"unanalyzed_{number:03}.py" for number in range(49)]
    stage = {
        "structured_tables": [source],
        "profile_coverage": {"unavailable_paths": unavailable, "sampled_unanalyzed_source_paths": unanalyzed},
    }
    original = deepcopy(stage)
    text = _pdf_text(stage)
    assert all(path in text for path in unavailable + unanalyzed)
    assert "Unavailable source paths" in text and "Unanalyzed sampled source paths" in text
    assert "Bounded profile coverage" in text
    assert text.count("NICO-TABLE-") == 1
    assert stage == original
