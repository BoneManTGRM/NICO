"""Exercise the actual final Mobile/WebKit consumer against observed UI evidence.

The old consumer rejected the real blob proof after browser verification passed.
These tests execute the workflow's observation assertions, including rejecting
source-only, missing, duplicated, or unverified download observations.
"""

import ast
import re
import textwrap
from pathlib import Path

import pytest

WORKFLOWS = (
    Path(".github/workflows/mobile-restart-production-proof.yml"),
    Path(".github/workflows/ios-webkit-paint-proof.yml"),
)
OBSERVATION_FIELDS = {
    "ui_review_pdf_source_artifact_reused",
    "ui_review_pdf_artifact_evidence_source",
    "ui_review_pdf_actual_blob_bytes_verified",
    "ui_review_pdf_actual_response_count",
    "ui_review_pdf_target_contract",
    "ui_review_pdf_target_blank_verified",
    "ui_review_pdf_noopener_noreferrer_verified",
    "ui_review_pdf_original_assessment_page_preserved",
    "ui_review_pdf_single_dispatch_verified",
    "ui_review_pdf_response_sha256_verified",
    "ui_review_pdf_exact_run_response_verified",
    "ui_review_pdf_exact_run_href_verified",
}


def _observation_gate(workflow: Path):
    source = workflow.read_text(encoding="utf-8")
    blocks = re.findall(
        r"(?m)^          python - <<'PY'\n(.*?)^          PY$",
        source,
        re.DOTALL,
    )
    blocks = [
        block for block in blocks
        if 'payload["ui_review_pdf_artifact_evidence_source"]' in block
    ]
    assert len(blocks) == 1, "The final evidence consumer must be exercised exactly once"
    parsed = ast.parse(textwrap.dedent(blocks[0]))
    selected = []
    observed_fields = set()
    for node in parsed.body:
        if not isinstance(node, ast.Assert):
            continue
        fields = {
            item.slice.value
            for item in ast.walk(node)
            if isinstance(item, ast.Subscript)
            and isinstance(item.value, ast.Name)
            and item.value.id == "payload"
            and isinstance(item.slice, ast.Constant)
            and item.slice.value in OBSERVATION_FIELDS
        }
        if fields:
            selected.append(node)
            observed_fields.update(fields)
    assert observed_fields == OBSERVATION_FIELDS, "Missing required UI observation gate"
    module = ast.Module(body=selected, type_ignores=[])
    return compile(ast.fix_missing_locations(module), str(workflow), "exec")


def _actual_response_and_blob_fixture():
    # Values observed in production Mobile job 111232289696 on 5ae43363.
    # The previous legacy label assertion rejected this stronger observation.
    return {
        "ui_review_pdf_source_artifact_reused": True,
        "ui_review_pdf_artifact_evidence_source": "observed-ui-response-and-verified-blob",
        "ui_review_pdf_actual_blob_bytes_verified": True,
        "ui_review_pdf_actual_response_count": 1,
        "ui_review_pdf_target_contract": "same-page-validated-blob-download",
        "ui_review_pdf_target_blank_verified": False,
        "ui_review_pdf_noopener_noreferrer_verified": False,
        "ui_review_pdf_original_assessment_page_preserved": True,
        "ui_review_pdf_single_dispatch_verified": True,
        "ui_review_pdf_response_sha256_verified": True,
        "ui_review_pdf_exact_run_response_verified": True,
        "ui_review_pdf_exact_run_href_verified": True,
    }


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=("chromium", "webkit"))
def test_final_consumer_accepts_the_observed_source_bound_ui_response(workflow):
    exec(_observation_gate(workflow), {"payload": _actual_response_and_blob_fixture()})


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=("chromium", "webkit"))
@pytest.mark.parametrize(
    ("field", "invalid"),
    (
        ("ui_review_pdf_source_artifact_reused", False),
        ("ui_review_pdf_artifact_evidence_source", "exact-sha-spanish-source-proof"),
        ("ui_review_pdf_artifact_evidence_source", "live-exact-artifact-response"),
        ("ui_review_pdf_actual_blob_bytes_verified", False),
        ("ui_review_pdf_actual_response_count", 0),
        ("ui_review_pdf_actual_response_count", 2),
        ("ui_review_pdf_actual_response_count", True),
        ("ui_review_pdf_actual_response_count", "1"),
        ("ui_review_pdf_target_contract", "blank-noopener-noreferrer"),
        ("ui_review_pdf_target_blank_verified", True),
        ("ui_review_pdf_noopener_noreferrer_verified", True),
        ("ui_review_pdf_original_assessment_page_preserved", False),
        ("ui_review_pdf_single_dispatch_verified", False),
        ("ui_review_pdf_response_sha256_verified", False),
        ("ui_review_pdf_exact_run_response_verified", False),
        ("ui_review_pdf_exact_run_href_verified", False),
    ),
)
def test_final_consumer_rejects_unverified_or_duplicate_observations(workflow, field, invalid):
    payload = _actual_response_and_blob_fixture()
    payload[field] = invalid
    with pytest.raises(AssertionError):
        exec(_observation_gate(workflow), {"payload": payload})


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=("chromium", "webkit"))
@pytest.mark.parametrize("field", sorted(OBSERVATION_FIELDS))
def test_final_consumer_rejects_missing_observations(workflow, field):
    payload = _actual_response_and_blob_fixture()
    del payload[field]
    with pytest.raises(KeyError):
        exec(_observation_gate(workflow), {"payload": payload})
