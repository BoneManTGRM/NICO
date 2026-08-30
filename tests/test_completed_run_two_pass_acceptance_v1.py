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
