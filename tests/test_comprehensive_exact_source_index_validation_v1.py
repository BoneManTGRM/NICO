from __future__ import annotations

import io

import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate

from nico import comprehensive_full_report_finish_v1 as finish
from nico.comprehensive_client_ready_projection_v1 import (
    render_compact_finding_register_pdf,
)
from nico.comprehensive_exact_source_index_validation_v1 import (
    compact_pdf_identifier,
    install_exact_source_index_validation_v1,
    validate_exact_source_index_identifiers,
)


RUN_ID = "comprun_a99bf09ec74e4c8a90c2922a626754f9"
FINDING_IDS = [
    f"RISK-P1-COMPREHENSIVE-EXACT-SOURCE-FINDING-{index:04d}"
    for index in range(1, 44)
]


def _findings(identifiers: list[str] = FINDING_IDS) -> list[dict[str, object]]:
    return [
        {
            "finding_id": identifier,
            "priority": "P1",
            "title": f"Exact-source regression finding {index}",
            "location": f"nico/module_{index:03d}.py:{100 + index}",
            "observed_evidence": "Bounded exact-source evidence retained.",
            "business_impact": "Requires human review.",
            "recommended_correction": "Review and verify the exact source location.",
            "verification": ["Confirm the exact immutable source anchor."],
        }
        for index, identifier in enumerate(identifiers, start=1)
    ]


def _canonical() -> dict[str, object]:
    code_findings = _findings()
    stages = [
        {"stage_id": f"worksheet_{index}", "title": title}
        for index, title in enumerate(finish._WORKSHEET_TITLES, start=1)
    ]
    stages.extend(
        {"stage_id": f"additional_{index}", "title": f"Additional Stage {index}"}
        for index in range(1, 5)
    )
    return {
        "identity": {
            "run_id": RUN_ID,
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "customer_id": "customer",
            "project_id": "project",
            "generated_at": "2026-08-05T10:30:00Z",
        },
        "assessment": {
            "sections": [{"id": "code_audit", "label": "Code Audit"}],
            "requested_scanner_records": 1,
        },
        "stage_summaries": stages,
        "scanner_execution_records": [
            {"scanner_name": "static", "completed": True, "state": "complete"}
        ],
        "canonical_scanner_finding_register": {"findings": []},
        "client_finding_remediation_register": {
            "code_findings": code_findings,
            "operational_findings": [],
            "summary": {
                "exact_source_code_finding_count": len(code_findings),
                "operational_or_context_finding_count": 0,
            },
        },
        "canonical_findings": code_findings,
        "artifact_manifest": {"artifacts": []},
        "approval": {"decision": "pending"},
    }


def _base_pdf() -> bytes:
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    lines = [
        "NICO Comprehensive Technical Assessment",
        *finish._WORKSHEET_TITLES,
        "Client Artifact Manifest",
        "Human Review and Exact-Artifact Approval Record",
        "Human Review and Acceptance Gate",
        "Generated: 2026-08-05T10:30:00Z",
    ]
    SimpleDocTemplate(buffer, invariant=1).build(
        [Paragraph(line, styles["BodyText"]) for line in lines]
    )
    return buffer.getvalue()


def _combined_pdf(index_findings: list[dict[str, object]]) -> bytes:
    register = {
        "code_findings": index_findings,
        "operational_findings": [],
        "summary": {
            "exact_source_code_finding_count": len(index_findings),
            "operational_or_context_finding_count": 0,
        },
    }
    register_pdf = render_compact_finding_register_pdf(register, spanish=False)
    writer = PdfWriter()
    for source in (_base_pdf(), register_pdf):
        for page in PdfReader(io.BytesIO(source)).pages:
            writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _surface_text() -> str:
    return "\n".join(
        [
            *finish._WORKSHEET_TITLES,
            "Client Artifact Manifest",
            "Human Review and Exact-Artifact Approval Record",
            "Human Review and Acceptance Gate",
            "Complete Exact-Source Index",
        ]
    )


def test_layout_normalization_accepts_only_wrapped_identifier_characters() -> None:
    identifier = FINDING_IDS[0]
    split = identifier.index("EXACT")
    extracted = "Complete Exact-Source Index\n" + identifier[:split] + "\n  " + identifier[split:]
    canonical = {
        "client_finding_remediation_register": {
            "code_findings": [{"finding_id": identifier}]
        }
    }

    assert validate_exact_source_index_identifiers(canonical, extracted) == 1
    assert compact_pdf_identifier(identifier) == compact_pdf_identifier(
        identifier[:split] + "\n" + identifier[split:]
    )
    assert compact_pdf_identifier(identifier) != compact_pdf_identifier(
        identifier[:-1] + "X"
    )


def test_full_validator_accepts_all_43_ids_in_wrapped_pdf_index() -> None:
    canonical = _canonical()
    pdf = _combined_pdf(_findings())
    status = install_exact_source_index_validation_v1()

    result = finish.assert_full_data_parity(
        canonical,
        _surface_text(),
        f"<article>{_surface_text()}</article>",
        pdf,
    )

    assert status["every_canonical_finding_id_required"] is True
    assert status["layout_whitespace_only_normalization"] is True
    assert result["exact_source_finding_count"] == 43
    assert result["proof_kind"] == "full_comprehensive"


def test_full_validator_still_fails_when_one_canonical_id_is_absent() -> None:
    canonical = _canonical()
    pdf = _combined_pdf(_findings(FINDING_IDS[:-1]))
    install_exact_source_index_validation_v1()

    with pytest.raises(
        ValueError,
        match=r"full-data PDF index omitted 1 canonical exact-source finding\(s\)",
    ):
        finish.assert_full_data_parity(
            canonical,
            _surface_text(),
            f"<article>{_surface_text()}</article>",
            pdf,
        )
