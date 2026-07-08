from nico.scanner_evidence import enrich_payload_with_scanner_evidence, scanner_section


def _scanner_payload():
    return {
        "scanner_results": [
            {
                "scanner": "bandit",
                "status": "passed",
                "evidence_summary": "bandit completed",
                "unavailable_data_notes": [],
            },
            {
                "scanner": "semgrep",
                "status": "unavailable",
                "evidence_summary": "semgrep unavailable",
                "unavailable_data_notes": ["semgrep is not installed"],
            },
        ]
    }


def test_scanner_worker_section_is_supplemental_diagnostic_only():
    section = scanner_section(_scanner_payload())

    assert section is not None
    assert section["id"] == "scanner_worker_evidence"
    assert section["status"] == "gray"
    assert section["diagnostic_status"] in {"yellow", "gray", "green", "red"}
    assert section["supplemental"] is True
    assert section["scoring_weight"] == 0
    assert section["score_impact"] == "diagnostic_only"


def test_enrich_payload_marks_scanner_evidence_as_supplemental():
    payload = {"sections": [{"id": "code_audit", "score": 90, "status": "green"}], **_scanner_payload()}

    result = enrich_payload_with_scanner_evidence(payload)
    section = next(item for item in result["sections"] if item["id"] == "scanner_worker_evidence")

    assert section["supplemental"] is True
    assert section["scoring_weight"] == 0
    assert result["evidence_readiness"]["scanner_worker_attached"] is True
    assert result["evidence_readiness"]["scanner_worker_scoring_mode"] == "supplemental_diagnostic"
