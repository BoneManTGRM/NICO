from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FINAL_REVIEW = ROOT / "apps" / "web" / "app" / "operations" / "final-review"
HYDRATION = (FINAL_REVIEW / "FinalReviewApprovedReportHydration.tsx").read_text(encoding="utf-8")
HANDOFF = (FINAL_REVIEW / "FinalReviewDownloadHandoff.tsx").read_text(encoding="utf-8")
LAYOUT = (FINAL_REVIEW / "layout.tsx").read_text(encoding="utf-8")


def test_successful_approval_rehydrates_exact_run_before_pdf_handoff() -> None:
    assert "REVIEW_DECISION_PATH" in HYDRATION
    assert 'requestMethod(input, init) !== "POST"' in HYDRATION
    assert "if (!reviewUrl || !approvalRequested(init))" in HYDRATION
    assert "const mutationResponse = await originalFetch.call(window, input, init)" in HYDRATION
    assert 'statusUrl.pathname = statusUrl.pathname.replace(/\\/review$/, "")' in HYDRATION
    assert 'method: "GET"' in HYDRATION
    assert 'cache: "no-store"' in HYDRATION
    assert "containsApprovedPdf(currentResponse)" in HYDRATION
    assert "return currentResponse" in HYDRATION
    assert "return mutationResponse" in HYDRATION
    assert "<FinalReviewApprovedReportHydration />" in LAYOUT


def test_one_tap_handoff_keeps_webkit_reservation_without_secondary_overlay() -> None:
    assert 'window.open("about:blank", "nico-comprehensive-pdf")' in HANDOFF
    assert "targetWindow.location.replace(href)" in HANDOFF
    assert 'data-final-review-pdf-handoff="ready"' not in HANDOFF
    assert 'data-final-review-pdf-open="true"' not in HANDOFF
    assert "PDF is ready" not in HANDOFF
    assert "Open PDF" not in HANDOFF
    assert 'position: "fixed"' not in HANDOFF
