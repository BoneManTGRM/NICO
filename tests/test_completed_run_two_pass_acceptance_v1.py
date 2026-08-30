from pathlib import Path

from scripts import completed_run_two_pass_acceptance_v1 as acceptance


def test_unified_waits_for_review_pdf_reentry_guard_between_real_clicks() -> None:
    class Page:
        def __init__(self) -> None:
            self.waits: list[int] = []

        def wait_for_timeout(self, milliseconds: int) -> None:
            self.waits.append(milliseconds)

    page = Page()

    acceptance._settle_review_pdf_reentry_guard(page)

    assert page.waits == [acceptance.REVIEW_PDF_REENTRY_SETTLEMENT_MS]
    assert acceptance.REVIEW_PDF_REENTRY_SETTLEMENT_MS > 1_500

    source = Path("scripts/completed_run_two_pass_acceptance_v1.py").read_text(
        encoding="utf-8"
    )
    first = source.index("first_pdf = recovery._verify_manifest_and_pdf")
    settlement = source.index("_settle_review_pdf_reentry_guard(page)", first)
    second = source.index("second_pdf = recovery._verify_manifest_and_pdf", settlement)
    assert first < settlement < second
