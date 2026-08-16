from __future__ import annotations

import io
from copy import deepcopy

import pytest
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate

from nico import comprehensive_full_report_finish_v1 as finish
from nico.comprehensive_full_data_worksheet_localization_v1 import (
    SPANISH_CANDIDATE_REGISTER,
    SPANISH_EXACT_SOURCE_INDEX,
    SPANISH_REVIEW_GATE,
    WORKSHEET_TITLES_BY_STAGE_ID,
    install_comprehensive_full_data_worksheet_localization_v1,
)

FINDING_ID = "NICO-CODE-SPANISH-FULL-DATA-0001"


def _canonical(*, spanish: bool = True, drop_stage: str | None = None) -> dict:
    stages = []
    for stage_id, (english_title, spanish_title) in WORKSHEET_TITLES_BY_STAGE_ID.items():
        if stage_id == drop_stage:
            continue
        stages.append(
            {
                "stage_id": stage_id,
                "title": spanish_title if spanish else english_title,
                "status": "review_required",
                "evidence": [f"retained evidence for {stage_id}"],
            }
        )
    stages.extend(
        {"stage_id": f"additional_{index}", "title": f"Additional Stage {index}"}
        for index in range(1, 5)
    )
    identity_language = "es-MX" if spanish else "en"
    return {
        # Intentionally stale root English on the Spanish fixture. Persisted run
        # identity must remain authoritative at terminal publication.
        "report_language": "en",
        "identity": {
            "run_id": "comprun_spanish_full_data_production_shape",
            "report_language": identity_language,
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "generated_at": "2026-08-16T17:00:00Z",
        },
        "assessment": {
            "report_language": identity_language,
            "sections": [{"id": "code_audit", "label": "Code Audit"}],
            "requested_scanner_records": 1,
            "stage_summaries": deepcopy(stages),
            "review_candidate_summary": {
                "review_required_total": 1,
                "verified_material_total": 0,
            },
        },
        "stage_summaries": stages,
        "scanner_execution_records": [
            {"scanner_name": "static", "completed": True, "state": "complete"}
        ],
        "review_candidate_summary": {
            "review_required_total": 1,
            "verified_material_total": 0,
        },
        "canonical_scanner_finding_register": {
            "findings": [{"candidate_id": "candidate-1", "status": "review_required"}]
        },
        "client_finding_remediation_register": {
            "code_findings": [
                {
                    "finding_id": FINDING_ID,
                    "priority": "P1",
                    "title": "Retained exact-source finding",
                    "location": "nico/example.py:42",
                }
            ]
        },
        "artifact_manifest": {"artifacts": []},
        "approval": {"decision": "pending"},
    }


def _spanish_surfaces(
    *,
    omit_worksheet: str | None = None,
    include_candidate: bool = True,
    include_gate: bool = True,
    include_index: bool = True,
    include_finding_id: bool = True,
) -> tuple[str, str, bytes]:
    worksheet_titles = [
        spanish_title
        for _english_title, spanish_title in WORKSHEET_TITLES_BY_STAGE_ID.values()
        if spanish_title != omit_worksheet
    ]
    markdown_lines = [f"## {title}" for title in worksheet_titles]
    if include_candidate:
        markdown_lines.append(f"## {SPANISH_CANDIDATE_REGISTER}")
    markdown = "\n".join(markdown_lines)
    rendered_html = "<html><body>" + "".join(
        f"<h2>{title}</h2>" for title in worksheet_titles
    ) + (f"<h2>{SPANISH_CANDIDATE_REGISTER}</h2>" if include_candidate else "") + "</body></html>"

    pdf_lines = [
        "Client Artifact Manifest",
        "Human Review and Exact-Artifact Approval Record",
        "Generated: 2026-08-16T17:00:00Z",
    ]
    if include_gate:
        pdf_lines.append(SPANISH_REVIEW_GATE)
    if include_index:
        pdf_lines.append(SPANISH_EXACT_SOURCE_INDEX)
    if include_finding_id:
        pdf_lines.append(FINDING_ID)

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    SimpleDocTemplate(buffer, invariant=1).build(
        [Paragraph(line, styles["BodyText"]) for line in pdf_lines]
    )
    return markdown, rendered_html, buffer.getvalue()


def _install(monkeypatch: pytest.MonkeyPatch):
    legacy_calls: list[tuple] = []

    def legacy_validator(*args):
        legacy_calls.append(args)
        return {"proof_kind": "legacy"}

    monkeypatch.setattr(finish, "assert_full_data_parity", legacy_validator)
    state = install_comprehensive_full_data_worksheet_localization_v1()
    return state, legacy_calls


def test_spanish_full_data_validates_actual_localized_sections_and_persisted_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, legacy_calls = _install(monkeypatch)
    markdown, rendered_html, pdf = _spanish_surfaces()

    proof = finish.assert_full_data_parity(_canonical(), markdown, rendered_html, pdf)

    assert state["localized_spanish_full_data_sections_required"] is True
    assert state["exact_source_identifiers_required"] is True
    assert state["persisted_report_language_authority"] is True
    assert state["established_stage_aliases_supported"] is True
    assert state["missing_worksheets_not_synthesized"] is True
    assert proof["proof_kind"] == "full_comprehensive"
    assert proof["localized_spanish_full_data_validation"] is True
    assert proof["worksheet_identity_source"] == "stable_stage_id_or_established_alias"
    assert proof["candidate_count"] == 1
    assert proof["exact_source_finding_count"] == 1
    assert legacy_calls == []


def test_established_review_companion_stage_aliases_are_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch)
    canonical = _canonical()
    aliases = {
        "historical_trends_and_change_failure": "historical_trends",
        "stakeholder_and_business_alignment": "stakeholder_alignment",
        "staffing_sequencing_and_cost": "resourcing",
    }
    for container in (canonical["stage_summaries"], canonical["assessment"]["stage_summaries"]):
        for stage in container:
            if stage.get("stage_id") in aliases:
                stage["stage_id"] = aliases[stage["stage_id"]]
    markdown, rendered_html, pdf = _spanish_surfaces()

    proof = finish.assert_full_data_parity(canonical, markdown, rendered_html, pdf)

    assert proof["proof_kind"] == "full_comprehensive"
    assert proof["worksheet_count"] == 8


def test_missing_canonical_worksheet_stage_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch)
    markdown, rendered_html, pdf = _spanish_surfaces()

    with pytest.raises(
        ValueError,
        match="full-data proof is missing human-review worksheets: Requirements Traceability",
    ):
        finish.assert_full_data_parity(
            _canonical(drop_stage="requirements_traceability"),
            markdown,
            rendered_html,
            pdf,
        )


def test_missing_spanish_worksheet_heading_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch)
    missing_title = WORKSHEET_TITLES_BY_STAGE_ID["six_month_roadmap"][1]
    markdown, rendered_html, pdf = _spanish_surfaces(omit_worksheet=missing_title)

    with pytest.raises(
        ValueError,
        match="full-data Spanish proof is missing localized human-review worksheets",
    ):
        finish.assert_full_data_parity(_canonical(), markdown, rendered_html, pdf)


def test_missing_spanish_candidate_register_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch)
    markdown, rendered_html, pdf = _spanish_surfaces(include_candidate=False)

    with pytest.raises(
        ValueError,
        match="missing the localized candidate register section",
    ):
        finish.assert_full_data_parity(_canonical(), markdown, rendered_html, pdf)


def test_missing_spanish_review_gate_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch)
    markdown, rendered_html, pdf = _spanish_surfaces(include_gate=False)

    with pytest.raises(ValueError, match="Puerta de revisión humana y aceptación"):
        finish.assert_full_data_parity(_canonical(), markdown, rendered_html, pdf)


def test_exact_source_identifier_must_exist_after_spanish_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch)
    markdown, rendered_html, pdf = _spanish_surfaces(include_finding_id=False)

    with pytest.raises(
        ValueError,
        match="full-data PDF index omitted 1 canonical exact-source finding",
    ):
        finish.assert_full_data_parity(_canonical(), markdown, rendered_html, pdf)


def test_english_full_data_path_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = _canonical(spanish=False)
    markdown = "english markdown"
    rendered_html = "<p>english html</p>"
    pdf = b"not-read-on-english-path"
    captured: dict[str, object] = {}

    def legacy_validator(canonical_arg, markdown_arg, html_arg, pdf_arg):
        captured.update(canonical=canonical_arg, markdown=markdown_arg, html=html_arg, pdf=pdf_arg)
        return {"proof_kind": "full_comprehensive"}

    monkeypatch.setattr(finish, "assert_full_data_parity", legacy_validator)
    install_comprehensive_full_data_worksheet_localization_v1()

    proof = finish.assert_full_data_parity(canonical, markdown, rendered_html, pdf)

    assert proof == {"proof_kind": "full_comprehensive"}
    assert captured == {
        "canonical": canonical,
        "markdown": markdown,
        "html": rendered_html,
        "pdf": pdf,
    }
