from __future__ import annotations

import nico.mid_assessment_report as report
import nico.mid_report_presentation as presentation


def _section(**overrides):
    section = {
        "id": "functional_qa",
        "label": "Functional QA",
        "score": None,
        "truth_status": "Unavailable",
        "summary": "Functional QA requires a functioning application or equivalent direct evidence.",
        "evidence": [],
        "findings": [],
        "unavailable": [
            "Functional QA requires a functioning application or equivalent direct evidence.",
            "No runnable build was attached.",
            "No runnable build was attached.",
        ],
        "missing_evidence_sources": ["application_url", "application_url"],
        "failed_evidence_tools": [],
        "source_classification": "unavailable",
        "direct_repository_proof": False,
        "human_review_required": False,
    }
    section.update(overrides)
    return section


def _payload(section):
    return {
        "report_id": "mid_report_test",
        "run_id": "midrun_test",
        "repository": "BoneManTGRM/NICO",
        "snapshot_commit_sha": "a" * 40,
        "source_identity_sha256": "b" * 64,
        "review_packet": {"review_packet_sha256": "c" * 64, "exceptions": []},
        "evidence_coverage": {"percent": 75, "numerator": 9, "denominator": 12, "method": "Explicit evidence units."},
        "sections": [section],
        "disclosures": ["Human review required."],
    }


def test_unscored_section_has_explicit_not_scored_label_and_deduplicated_limits():
    normalized = presentation.normalized_section_payload(_section())

    assert normalized["score"] is None
    assert normalized["score_label"] == "NOT SCORED"
    assert normalized["unavailable"] == ["No runnable build was attached."]
    assert normalized["missing_evidence_sources"] == ["application_url"]
    assert normalized["presentation_version"] == presentation.MID_REPORT_PRESENTATION_VERSION


def test_numeric_scores_remain_truthful():
    normalized = presentation.normalized_section_payload(_section(score=82.5, truth_status="Verified with limitations"))

    assert normalized["score"] == 82.5
    assert normalized["score_label"] == "82.5/100"


def test_html_uses_collapsed_details_and_never_renders_empty_score_denominator():
    rendered = presentation.collapsible_mid_report_html(_payload(_section()))

    assert "NOT SCORED" in rendered
    assert "null/100" not in rendered
    assert "undefined/100" not in rendered
    assert "· /100" not in rendered
    assert "<details>" in rendered
    assert "Evidence (" not in rendered
    assert "Limitations and missing evidence (2)" in rendered
    assert rendered.count("No runnable build was attached.") == 1
    assert "Missing source: application_url" in rendered


def test_html_preserves_real_numeric_score_and_exception_reason():
    payload = _payload(_section(score=88, truth_status="Verified"))
    payload["review_packet"]["exceptions"] = [
        {"title": "Review scanner limitation", "severity": "medium", "reason": "Human validation is still required."}
    ]

    rendered = presentation.collapsible_mid_report_html(payload)

    assert "88/100" in rendered
    assert "Review scanner limitation" in rendered
    assert "Human validation is still required." in rendered


def test_installer_rebinds_report_functions_idempotently(monkeypatch):
    monkeypatch.setattr(report, "_nico_mid_report_presentation_installed", False, raising=False)
    monkeypatch.setattr(report, "_section_payload", presentation._ORIGINAL_SECTION_PAYLOAD)
    monkeypatch.setattr(report, "_html", presentation._ORIGINAL_HTML)

    first = presentation.install_mid_report_presentation()
    second = presentation.install_mid_report_presentation()

    assert first["status"] == "installed"
    assert second["status"] == "already_installed"
    assert report._section_payload is presentation.normalized_section_payload
    assert report._html is presentation.collapsible_mid_report_html
