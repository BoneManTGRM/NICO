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
    assert all(row[0] in text for row in table["rows"][:15])
    assert not any(row[0] in text for row in table["rows"][15:])
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


@pytest.mark.parametrize("spanish", [False, True])
def test_large_component_and_interaction_previews_are_exact_deterministic_and_bound(spanish):
    components = _table(2499)
    components["columns"] = ["Source", "Kind", "Language"]
    components["rows"] = [[f"component_{i:05}.py", "source_module", "Python"] for i in range(2499)]
    interactions = {"title": "Source interactions and potential boundaries",
        "columns": ["Source", "Operation", "Target", "Potential boundary", "Line"],
        "rows": [[f"interaction_{i:05}.py", "import", f"target_{i:05}", "None", i+1] for i in range(21802)]}
    stage = {"structured_tables": [components, interactions]}
    before = deepcopy(stage)
    hashes = [source_table_summary(table)["sha256"] for table in stage["structured_tables"]]
    text = _pdf_text(stage, spanish=spanish)
    assert text == _pdf_text(stage, spanish=spanish)
    for table, shown in ((components, 15), (interactions, 24)):
        assert sum(row[0] in text for row in table["rows"]) == shown
        assert all(row[0] in text for row in table["rows"][:shown])
        count = f"{shown} de {len(table['rows'])}" if spanish else f"{shown} of {len(table['rows'])}"
        assert count in " ".join(text.split())
    assert ("vista previa" if spanish else "preview") in text
    assert all(digest in "".join(text.split()) for digest in hashes)
    assert stage == before
    assert [source_table_summary(table)["sha256"] for table in stage["structured_tables"]] == hashes


def _large_inventory():
    def value(prefix, i):
        return f'{prefix}_{i:05}.py'
    return {'structured_tables': [
        {'title': 'Observed source components', 'columns': ['Source', 'Kind', 'Language'],
         'rows': [[value('component', i), 'source_module', 'Python'] for i in range(2499)]},
        {'title': 'Source interactions and potential boundaries',
         'columns': ['Source', 'Operation', 'Target', 'Potential boundary', 'Line'],
         'rows': [[value('interaction', i), 'import', value('target', i),
                   'incoming_request_authorization_unverified', i+1] for i in range(21802)]},
    ]}


def _preview_pdf(stage, spanish):
    output = io.BytesIO()
    SimpleDocTemplate(output, pagesize=(612, 792), invariant=1).build(
        _source_pdf_tables(stage, spanish=spanish, width=468))
    return output.getvalue()


@pytest.mark.parametrize('spanish', [False, True])
def test_long_preview_cells_wrap_and_disclose_truncation_without_mutating_evidence(spanish):
    # Only preview rows need pathological lengths; untouched tail still tests counts.
    stage = _large_inventory()
    for table in stage['structured_tables']:
        for row in table['rows'][:24]:
            row[0] += 'W'*4000 + '<tag>&\nTAIL_NOT_INLINE'
            if len(row) == 5: row[2] += 'W'*4000 + '<tag>&\nTAIL_NOT_INLINE'
    original = json.dumps(stage, sort_keys=True)
    blob = _preview_pdf(stage, spanish)
    assert blob == _preview_pdf(stage, spanish)
    reader = PdfReader(io.BytesIO(blob))
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    assert 'TAIL_NOT_INLINE' not in text
    assert '…' in text
    assert ('truncadas a 80 caracteres' if spanish else 'truncated to 80 characters') in ' '.join(text.split())
    assert sum(f'component_{i:05}' in text for i in range(2499)) == 15
    assert sum(f'interaction_{i:05}' in text for i in range(21802)) == 24
    assert json.dumps(stage, sort_keys=True) == original
    assert len(reader.pages) <= 4


@pytest.mark.parametrize('spanish', [False, True])
def test_preview_preservation_at_sixty_pages_and_fail_closed_overflow(spanish):
    from pypdf import PdfWriter
    from tests.test_client_pdf_compose_v2 import _pdf
    from nico.client_pdf_compose_v2 import compose_compact_client_pdf
    stage = _large_inventory()
    preview = _preview_pdf(stage, spanish)
    preview_pages = len(PdfReader(io.BytesIO(preview)).pages)
    assert preview_pages <= 4  # Four pages remain after the observed Spanish56 baseline.
    def compose(total):
        writer = PdfWriter()
        primary = total - preview_pages - 2
        for blob in (_pdf(*[[f'Primary evidence {i}'] for i in range(primary)]), preview):
            writer.append(PdfReader(io.BytesIO(blob)))
        output = io.BytesIO(); writer.write(output)
        return compose_compact_client_pdf(output.getvalue(), _pdf(['Register']), _pdf(['Gate']), page_limit=60)
    result = compose(60)
    reader = PdfReader(io.BytesIO(result))
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    assert len(reader.pages) == 60
    assert all(f'component_{i:05}.py' in text for i in range(15))
    assert all(f'interaction_{i:05}.py' in text for i in range(24))
    assert 'Register' in text and 'Gate' in text
    with pytest.raises(ValueError, match='60-page boundary'):
        compose(61)


@pytest.mark.parametrize('spanish', [False, True])
def test_actual_preview_pdf_remains_bound_to_complete_canonical_export_and_gates(spanish):
    import base64
    from tests.test_source_table_export_binding import _canonical, _package
    from nico.source_table_export_binding import capture_source_table_evidence, validate_source_table_evidence
    stage = _large_inventory()
    canonical = _canonical(*stage['structured_tables'], language='es-MX' if spanish else 'en')
    canonical['assessment'] = {'technical_score': 92, 'evidence_adjusted_score': 88}
    canonical['canonical_findings'] = [{'finding_id': f'SYNTHETIC-{i}', 'status': 'open'} for i in range(7)]
    original = deepcopy(canonical)
    expected = capture_source_table_evidence(canonical)
    package = _package(canonical)
    original_export = package['canonical_json']
    original_hash = package['canonical_json_sha256']
    pdf = _preview_pdf(package['json']['stage_summaries'][0], spanish)
    package['pdf_base64'] = base64.b64encode(pdf).decode('ascii')
    package['pdf_sha256'] = hashlib.sha256(pdf).hexdigest()
    assert validate_source_table_evidence(expected, package)
    assert package['json'] == original
    assert package['canonical_json'] == original_export
    assert package['canonical_json_sha256'] == original_hash
    assert package['approval_status'] == 'pending_human_approval'
    assert package['human_review_required'] is True
    assert package['human_review_completed'] is False
    assert package['client_delivery_allowed'] is False
