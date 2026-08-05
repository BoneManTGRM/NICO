from __future__ import annotations

import io

import pytest
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate

from nico.comprehensive_client_surface_structure_cleanup_v1 import (
    client_surface_values,
    sanitize_client_rendered_stage,
)
from nico.comprehensive_full_report_finish_v1 import (
    assert_no_raw_mapping_presentation,
)
from nico.comprehensive_raw_mapping_string_recovery_v1 import (
    install_raw_mapping_string_recovery_v1,
    recover_literal_structure,
)


RAW_OUTCOME_TAXONOMY = (
    "Outcome taxonomy: {'failure': 19, 'neutral': 0, 'skipped': 0, "
    "'success': 80, 'unknown': 1, 'cancelled': 0, 'timed_out': 0, "
    "'action_required': 0, 'queued_or_in_progress': 0}"
)


def _pdf(line: str) -> bytes:
    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, invariant=1).build(
        [Paragraph(line, getSampleStyleSheet()["BodyText"])]
    )
    return buffer.getvalue()


def test_prefixed_outcome_taxonomy_is_recovered_as_labelled_structure() -> None:
    recovered = recover_literal_structure(RAW_OUTCOME_TAXONOMY)

    assert recovered == {
        "Outcome taxonomy": {
            "failure": 19,
            "neutral": 0,
            "skipped": 0,
            "success": 80,
            "unknown": 1,
            "cancelled": 0,
            "timed_out": 0,
            "action_required": 0,
            "queued_or_in_progress": 0,
        }
    }


def test_exact_failed_taxonomy_line_renders_without_python_mapping_syntax() -> None:
    status = install_raw_mapping_string_recovery_v1()

    rendered = client_surface_values(
        [RAW_OUTCOME_TAXONOMY],
        limit=1,
        item_limit=100_000,
    )

    assert status["labelled_mapping_tails_recovered"] is True
    assert rendered == [
        "Outcome Taxonomy: Failed: 19; Successful: 80; Unknown: 1"
    ]
    assert "{" not in rendered[0]
    assert "}" not in rendered[0]
    assert "'failure'" not in rendered[0]


def test_stage_projection_converts_taxonomy_before_final_publication_validation() -> None:
    install_raw_mapping_string_recovery_v1()
    stage = {
        "stage_id": "historical_trends_and_change_failure",
        "title": "Historical Trends and Change Failure",
        "evidence": [RAW_OUTCOME_TAXONOMY],
        "findings": [],
        "unavailable": [],
    }

    cleaned = sanitize_client_rendered_stage(stage)
    line = cleaned["evidence"][0]

    with pytest.raises(ValueError, match="raw mapping presentation"):
        assert_no_raw_mapping_presentation(
            RAW_OUTCOME_TAXONOMY,
            f"<p>{RAW_OUTCOME_TAXONOMY}</p>",
            _pdf(RAW_OUTCOME_TAXONOMY),
        )

    assert_no_raw_mapping_presentation(line, f"<p>{line}</p>", _pdf(line))
    assert stage["evidence"] == [RAW_OUTCOME_TAXONOMY]
    assert "{" not in line
    assert "Successful: 80" in line
