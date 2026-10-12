"""A retained scanner status record is not proof of scanner execution."""
from copy import deepcopy
import base64
import io

import pytest
from pypdf import PdfReader

from nico.comprehensive_human_review_package_cleanup_v1 import build_scanner_execution_stage
from tests.test_comprehensive_human_review_package_cleanup_v1 import _Renderer


NOTE = "Status record retention does not establish raw execution evidence."
NOTE_ES = "La conservación del registro de estado no acredita evidencia sin procesar de la ejecución."


@pytest.mark.parametrize("state", ["unavailable", "completed_clean", "completed_with_findings"])
@pytest.mark.parametrize("retained", [False, True])
def test_record_retention_is_named_without_granting_execution_credit(state, retained):
    record = {"scanner_name": "typescript", "state": state,
              "completed": state.startswith("completed"), "exact_commit_match": True,
              "artifact_hash": "a" * 64 if retained else "", "findings": [],
              "failure_reason": "Project commands remain disabled."}
    canonical = {"scanner_execution_records": [record],
                 "assessment": {"technical_score": 92, "canonical_evidence_adjusted_score": 88}}
    before = deepcopy(canonical)
    stage = build_scanner_execution_stage(canonical, _Renderer)
    line = next(row for row in stage["evidence"] if row.startswith("typescript:"))
    assert f"status record={'retained' if retained else 'missing'};" in line
    assert "; artifact=" not in line
    assert NOTE in stage["evidence"]
    assert stage["status"] == ("complete" if record["completed"] else "review_required")
    assert stage["unavailable"] == ([] if record["completed"] else
                                     ["typescript: Project commands remain disabled."])
    assert canonical == before


@pytest.mark.parametrize("language,label,note", [
    ("en", "status record=retained", NOTE),
    ("es-MX", "registro de estado=conservado", NOTE_ES),
])
def test_unavailable_record_copy_survives_public_markdown_html_and_pdf(language, label, note):
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from tests.test_v2_premium_report_renderer import _package

    package = _package(language)
    package["json"]["scanner_execution_records"] = [{
        "scanner_name": "typescript", "state": "unavailable", "status": "unavailable",
        "completed": False, "verified": False, "exact_commit_match": True,
        "artifact_hash": "a" * 64, "findings": [],
    }]
    before = deepcopy(package)
    result = rebuild_client_artifacts(package)
    pdf = PdfReader(io.BytesIO(base64.b64decode(result["pdf_base64"])))
    pdf_text = " ".join(" ".join(page.extract_text() or "" for page in pdf.pages).split())
    for rendered in [result["markdown"], result["html"], pdf_text]:
        assert label in rendered
        assert note in rendered
    row = result["json"]["scanner_execution_records"][0]
    for key, value in before["json"]["scanner_execution_records"][0].items():
        assert row[key] == value
    assert row["raw_artifact_retention_complete"] is False
    assert row["verified_complete"] is False
    for key in ["technical_score", "canonical_evidence_adjusted_score"]:
        assert result["json"]["assessment"][key] == before["json"]["assessment"][key]
    assert len(result["json"]["canonical_findings"]) == 1
    for key in ["finding_id", "title", "location", "status"]:
        assert result["json"]["canonical_findings"][0][key] == before["json"]["canonical_findings"][0][key]
    assert package == before
