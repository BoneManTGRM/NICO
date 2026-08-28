from __future__ import annotations

import base64
from copy import deepcopy

from nico import comprehensive_same_run_locale_report_v1 as same_run
from nico import comprehensive_spanish_canonical_report_v87 as spanish_renderer
from nico import comprehensive_spanish_presentation_parity_v1 as spanish
from nico.comprehensive_current_report_truth_parity_v1 import (
    install_comprehensive_current_report_truth_parity_v1,
)
from nico.comprehensive_report_package import _canonical_hash
from nico.comprehensive_report_semantic_manifest_v1 import (
    CANONICAL_TOC_SECTION_IDS,
    CANONICAL_TOC_TITLES,
    SECTION_TITLE_ES_BY_EN,
)


CONTINUATION_EN = "Compact Finding and Remediation Register · continuation"
CONTINUATION_ES = "Registro compacto de hallazgos y remediación · continuación"


def test_spanish_compact_register_continuation_survives_manifest_install() -> None:
    state = install_comprehensive_current_report_truth_parity_v1()

    assert state["canonical_semantic_report_manifest"] is True
    assert SECTION_TITLE_ES_BY_EN[CONTINUATION_EN] == CONTINUATION_ES
    assert spanish._TITLE_MAP[CONTINUATION_EN] == CONTINUATION_ES
    assert CONTINUATION_EN not in CANONICAL_TOC_TITLES


def test_repository_and_reconciliation_sections_share_one_locale_manifest() -> None:
    state = install_comprehensive_current_report_truth_parity_v1()
    assert state["canonical_semantic_report_manifest"] is True

    repository_index = CANONICAL_TOC_SECTION_IDS.index("repository_delivery_evidence")
    reconciliation_index = CANONICAL_TOC_SECTION_IDS.index(
        "evidence_reconciliation_scoring"
    )
    assert reconciliation_index == repository_index + 1
    assert CANONICAL_TOC_TITLES[repository_index] == "Repository and Delivery Evidence"
    assert CANONICAL_TOC_TITLES[reconciliation_index] == (
        "Evidence Reconciliation and Scoring"
    )
    assert SECTION_TITLE_ES_BY_EN["Repository and Delivery Evidence"] == (
        "Evidencia del repositorio y de entrega"
    )
    assert SECTION_TITLE_ES_BY_EN["Evidence Reconciliation and Scoring"] == (
        "Conciliación y puntuación de evidencia"
    )


def test_same_run_locale_renderers_consume_identical_stage_topology() -> None:
    canonical = {
        "identity": {
            "run_id": "comprun_topology_parity",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "generated_at": "2026-08-25T14:33:26Z",
        },
        "assessment": {},
        "stage_summaries": [
            {
                "stage_id": "repository_delivery_evidence",
                "title": "Repository and Delivery Evidence",
                "status": "COMPLETE",
                "summary": "Exact-commit repository evidence retained.",
            },
            {
                "stage_id": "evidence_reconciliation_and_scoring",
                "title": "Evidence Reconciliation and Scoring",
                "status": "COMPLETE",
                "summary": "Canonical evidence and score truth reconciled.",
            },
        ],
    }

    _, _, english_stages, _ = same_run._render_inputs(canonical)
    _, _, spanish_stages, _ = spanish_renderer._render_inputs(canonical)

    expected_ids = [
        "repository_delivery_evidence",
        "evidence_reconciliation_and_scoring",
    ]
    assert [item["stage_id"] for item in english_stages] == expected_ids
    assert [item["stage_id"] for item in spanish_stages] == expected_ids
    assert [item["title"] for item in english_stages] == [
        "Repository and Delivery Evidence",
        "Evidence Reconciliation and Scoring",
    ]
    assert [item["title"] for item in spanish_stages] == [
        "Evidencia del repositorio y de entrega",
        "Conciliación y puntuación de evidencia",
    ]


def test_locale_change_reuses_same_frozen_run_without_assessment_rerun(monkeypatch) -> None:
    canonical = {
        "service_id": "comprehensive",
        "report_language": "en",
        "identity": {
            "run_id": "comprun_locale_closure",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "evidence_ledger_id": "ledger_locale_closure",
            "report_language": "en",
            "generated_at": "2026-08-25T14:33:26Z",
        },
        "assessment": {
            "report_language": "en",
            "maturity_signal": {"score": 93, "presented_score": 93},
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        "stage_summaries": [],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    truth_sha = _canonical_hash(canonical)
    status = {
        "run_id": canonical["identity"]["run_id"],
        "repository": canonical["identity"]["repository"],
        "commit_sha": canonical["identity"]["commit_sha"],
        "evidence_ledger_id": canonical["identity"]["evidence_ledger_id"],
        "report_language": "en",
        "terminal": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "reports": {
            "report_id": "report_locale_closure",
            "canonical_truth_sha256": truth_sha,
            "json": canonical,
            "markdown": "# source",
            "html": "<article>source</article>",
            "pdf_base64": base64.b64encode(b"%PDF-1.4\nsource").decode("ascii"),
        },
    }
    before = deepcopy(status)
    localized_pdf = b"%PDF-1.4\nes-MX"
    monkeypatch.setattr(
        same_run,
        "_render_target",
        lambda frozen, language: {
            "markdown": "# informe",
            "html": "<article>informe</article>",
            "pdf_base64": base64.b64encode(localized_pdf).decode("ascii"),
            "pdf_sha256": same_run.hashlib.sha256(localized_pdf).hexdigest(),
            "pdf_page_count": 44,
        },
    )

    result = same_run.build_same_run_locale_report(status, "es-MX")

    assert status == before
    assert result["run_id"] == canonical["identity"]["run_id"]
    assert result["report_language"] == "es-MX"
    assert result["same_canonical_run"] is True
    assert result["assessment_rerun"] is False
    assert result["canonical_truth_preserved"] is True
    assert result["canonical_truth_sha256"] == truth_sha
    assert result["report"]["json"] == canonical
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
