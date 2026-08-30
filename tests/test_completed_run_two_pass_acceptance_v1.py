import ast
import hashlib
import json
from pathlib import Path

from scripts.comprehensive_production_run_handoff_v1 import (
    retain_unified_english_pdf,
)


def test_unified_waits_for_review_pdf_reentry_guard_between_real_clicks() -> None:
    source = Path("scripts/completed_run_two_pass_acceptance_v1.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    settlement_ms = next(
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "REVIEW_PDF_REENTRY_SETTLEMENT_MS"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, int)
    )
    assert settlement_ms > 1_500
    assert "page.wait_for_timeout(REVIEW_PDF_REENTRY_SETTLEMENT_MS)" in source

    first = source.index("first_pdf = recovery._verify_manifest_and_pdf")
    settlement = source.index("_settle_review_pdf_reentry_guard(page)", first)
    second = source.index("second_pdf = recovery._verify_manifest_and_pdf", settlement)
    assert first < settlement < second


def test_unified_reuses_verified_first_pass_truth_before_fresh_final_read() -> None:
    source = Path("scripts/completed_run_two_pass_acceptance_v1.py").read_text(
        encoding="utf-8"
    )

    first_pass = source.index("first_pass = _run_pass(")
    second_pass = source.index("second_pass = _run_pass(", first_pass)
    reuse = source.index(
        'verified_canonical_truth=first_pass["canonical_truth"]', second_pass
    )
    fresh_final_read = source.index(
        "request = playwright.request.new_context", reuse
    )

    assert "def _reuse_verified_canonical_truth(" in source
    assert "canonical_truth_digest_computed_from_json" in source
    assert "canonical_truth_reused_from_pass" in source
    assert first_pass < second_pass < reuse < fresh_final_read


def test_unified_retains_exact_source_bound_english_pdf_for_phase1_binder(
    tmp_path: Path,
) -> None:
    pdf_bytes = b"%PDF-1.4\n" + (b"verified-source-pdf\n" * 80)
    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    source_dir = tmp_path / "source-proof"
    source_dir.mkdir()
    source_pdf = source_dir / "nico-comprehensive-en-automated-draft.pdf"
    source_pdf.write_bytes(pdf_bytes)
    source_proof = source_dir / "spanish-comprehensive-live-proof.json"
    source_proof.write_text(
        json.dumps(
            {
                "run_id": "comprun_exact_source_pdf",
                "expected_sha": "a" * 40,
                "repository": "BoneManTGRM/NICO",
                "same_run_bilingual_pdf_verified": True,
                "same_run_bilingual_assessment_rerun": False,
                "localized_pdf_artifact_hash_headers_verified": True,
                "human_review_required": True,
                "client_delivery_allowed": False,
                "english_pdf_path": f"audit-results/{source_pdf.name}",
                "english_pdf_sha256": pdf_sha256,
            }
        ),
        encoding="utf-8",
    )

    retained = retain_unified_english_pdf(
        source_proof,
        tmp_path / "unified-artifacts",
        run_id="comprun_exact_source_pdf",
        expected_sha="a" * 40,
        repository="BoneManTGRM/NICO",
        expected_download_sha256=pdf_sha256,
    )

    retained_path = Path(retained["path"])
    assert retained_path.name == "pass-2-comprehensive.pdf"
    assert retained_path.read_bytes() == pdf_bytes
    assert retained["sha256"] == pdf_sha256
    assert retained["size_bytes"] == len(pdf_bytes)
    assert retained["human_review_required"] is True
    assert retained["client_delivery_allowed"] is False
