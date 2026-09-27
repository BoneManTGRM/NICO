from copy import deepcopy

import pytest

from nico import phase17_canonical_artifact_rebuild_v1 as phase17


def _eligible():
    return {"json": {
        "assessment": {"canonical_scanner_finding_register": {
            "findings": [{"candidate_id": "raw-1", "literal": "Exact evidence"}],
            "candidate_record_count": 1,
            "count_parity_verified": True,
            "candidate_record_count_matches_raw": True,
            "raw_payload_retention_complete": True,
            "mutually_exclusive_dispositions_verified": True,
            "projection_redaction_preserves_source_fingerprints": True,
            "totals": {"unavailable": 1},
        }},
        "client_finding_remediation_register": {"code_findings": []},
        "v2_pipeline_contract": {
            "authoritative_premium_truth_projection": True,
            "structured_finding_remediation_register": True,
            "full_evidence_retained_outside_client_pdf": True,
        },
        "v2_prepublication_contract": {
            "final_register_count_synchronized_before_render": True,
            "comprehensive_client_truth_final_version": "nico.comprehensive-client-truth-final.v1",
        },
        "human_review_required": True, "client_delivery_allowed": False,
    }}


def test_transient_render_restores_exact_evidence_and_isolation():
    source = _eligible()
    original = deepcopy(source)
    render_input, retained, compact = phase17._bounded_localized_preparation_input(source)
    assert render_input["json"]["assessment"]["canonical_scanner_finding_register"]["findings"] == []
    rendered = deepcopy(render_input)
    rendered["pdf_base64"] = "exact-rendered-bytes"
    result = phase17._restore_render_scanner_register(rendered, retained, compact)
    assert result["json"] == original["json"]
    assert result["pdf_base64"] == "exact-rendered-bytes"
    assert source == original
    result["json"]["assessment"]["canonical_scanner_finding_register"]["findings"][0]["literal"] = "output only"
    assert source == original


@pytest.mark.parametrize("change", ["missing", "count", "status", "findings", "count_bool", "flag_int"])
def test_unexpected_render_metadata_cannot_be_hidden(change):
    source = _eligible()
    render_input, retained, compact = phase17._bounded_localized_preparation_input(source)
    rendered = deepcopy(render_input)
    register = rendered["json"]["assessment"]["canonical_scanner_finding_register"]
    if change == "missing":
        del rendered["json"]["assessment"]["canonical_scanner_finding_register"]
    elif change == "count":
        register["candidate_record_count"] = 0
    elif change == "status":
        register["totals"]["unavailable"] = 0
    elif change == "count_bool":
        register["candidate_record_count"] = True
    elif change == "flag_int":
        register["count_parity_verified"] = 1
    else:
        register["findings"] = [{"candidate_id": "unexpected"}]
    with pytest.raises(ValueError, match="render_scanner_register_metadata_changed"):
        phase17._restore_render_scanner_register(rendered, retained, compact)


@pytest.mark.parametrize("field", ["v2_pipeline_contract", "v2_prepublication_contract", "client_finding_remediation_register"])
def test_ineligible_inputs_remain_whole(field):
    source = _eligible()
    del source["json"][field]
    actual, retained, compact = phase17._bounded_localized_preparation_input(source)
    assert actual is source and retained is None and compact is None
    assert actual["json"]["assessment"]["canonical_scanner_finding_register"]["findings"]


@pytest.mark.parametrize("locale", ["en", "es-MX"])
def test_real_bilingual_single_pass_preserves_visible_content(locale, monkeypatch):
    import base64
    import io
    from pypdf import PdfReader
    from tests.test_v2_premium_report_renderer import _package
    from tests.test_comprehensive_same_run_locale_report_v1 import _install_finalized_scanner_register

    prepared = phase17._prepare_client_artifact_package(_package(locale))
    retained = _install_finalized_scanner_register(prepared["json"])
    # Preparation supplies every publication contract; the fixture supplies only
    # one synthetic raw candidate, independent of the real decision register.
    with monkeypatch.context() as patch:
        patch.setattr(phase17, "_bounded_localized_preparation_input", lambda value: (value, None, None))
        expected = phase17.rebuild_single_pass_premium_artifacts(prepared)
    compacted = []
    original_helper = phase17._bounded_localized_preparation_input
    def capture(value):
        result = original_helper(value)
        compacted.append(result[1] is not None)
        return result
    monkeypatch.setattr(phase17, "_bounded_localized_preparation_input", capture)
    actual = phase17.rebuild_single_pass_premium_artifacts(prepared)
    assert compacted == [True]
    assert actual["json"]["assessment"]["canonical_scanner_finding_register"] == expected["json"]["assessment"]["canonical_scanner_finding_register"]
    assert actual["markdown"] == expected["markdown"]
    assert actual["html"] == expected["html"]
    def text(package):
        return [page.extract_text() for page in PdfReader(io.BytesIO(base64.b64decode(package["pdf_base64"]))).pages]
    assert text(actual) == text(expected)
    assert actual["json"] == expected["json"]
    assert actual["human_review_required"] is True
    assert actual["client_delivery_allowed"] is False
