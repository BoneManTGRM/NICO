import ast
from pathlib import Path


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
