from nico.full_report_artifact_identity_v4 import build_full_artifact_identity, build_full_artifact_manifest


def released_result():
    return {"report_version": "full-10.0", "full_production_release": {"client_delivery_allowed": True}}


def test_identity_is_stable_and_content_bound():
    first = build_full_artifact_identity(assessment_id="assessment-123", locale="en-US", format="pdf", content=b"report bytes", report_version="full-10.0")
    second = build_full_artifact_identity(assessment_id="assessment-123", locale="en", format="pdf", content=b"report bytes", report_version="full-10.0")
    changed = build_full_artifact_identity(assessment_id="assessment-123", locale="en", format="pdf", content=b"changed report bytes", report_version="full-10.0")
    assert first == second
    assert first.artifact_id != changed.artifact_id
    assert first.sha256 != changed.sha256
    assert first.filename.endswith(".pdf")


def test_manifest_requires_all_three_formats():
    manifest = build_full_artifact_manifest(released_result(), {"pdf": b"pdf", "html": "report"}, assessment_id="assessment-123", locale="en")
    assert manifest["persisted_artifacts_complete"] is False
    assert manifest["client_delivery_allowed"] is False
    assert "Missing persisted Full markdown artifact." in manifest["issues"]


def test_manifest_allows_complete_released_artifacts():
    manifest = build_full_artifact_manifest(released_result(), {"pdf": b"pdf", "html": "report", "markdown": "report"}, assessment_id="assessment-123", locale="es-MX")
    assert manifest["locale"] == "es"
    assert manifest["persisted_artifacts_complete"] is True
    assert manifest["client_delivery_allowed"] is True
    assert set(manifest["artifacts"]) == {"pdf", "html", "markdown"}
