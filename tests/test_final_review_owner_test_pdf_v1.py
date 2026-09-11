from pathlib import Path


WORKSPACE = Path(
    "apps/web/app/operations/final-review/ComprehensiveFinalReviewWorkspace.tsx"
).read_text(encoding="utf-8")
HANDOFF = Path(
    "apps/web/app/operations/final-review/FinalReviewDownloadHandoff.tsx"
).read_text(encoding="utf-8")
PAGE = Path("apps/web/app/operations/final-review/page.tsx").read_text(encoding="utf-8")
STRATEGIC = Path("apps/web/app/assessment/strategicEvidence.ts").read_text(encoding="utf-8")


def owner_test_branch() -> str:
    return WORKSPACE.split("if (!canonicalApprovalReady) {", 1)[1].split(
        "if (!exactEditionDownloaded)", 1
    )[0]


def test_owner_can_open_exact_run_without_human_identity() -> None:
    assert "const operatorReady = Boolean(runId.trim() && adminToken.trim());" in WORKSPACE
    assert (
        "const canonicalApprovalReady = Boolean(operatorReady && reviewer.trim() && reviewerRole.trim());"
        in WORKSPACE
    )
    load = WORKSPACE.split("async function loadStatus", 1)[1].split(
        "async function submitDecision", 1
    )[0]
    assert "if (!operatorReady)" in load
    assert "canonicalApprovalReady" not in load


def test_owner_test_uses_exact_real_pdf_and_does_not_record_approval() -> None:
    branch = owner_test_branch()
    assert "await downloadApprovedPdf(result, ownerTestFilename)" in branch
    assert "OWNER-TEST-NON-DELIVERABLE.pdf" in branch
    assert "submitDecision" not in branch
    assert "reviewUrl()" not in branch
    assert "deliveryAuthorizationUrl" not in branch
    assert "delivery_authorized" not in branch
    assert "setResult" not in branch
    assert "Human approval was not recorded and client delivery remains blocked." in WORKSPACE


def test_owner_test_keeps_pdf_integrity_validation() -> None:
    verifier = WORKSPACE.split("async function downloadBase64Pdf", 1)[1].split(
        "async function responseError", 1
    )[0]
    assert 'String.fromCharCode(...bytes.slice(0, 4)) !== "%PDF"' in verifier
    assert 'window.crypto.subtle.digest("SHA-256", buffer)' in WORKSPACE
    assert "actualSha256 !== expectedSha256.toLowerCase()" in verifier


def test_real_approval_still_requires_reviewer_identity_and_exact_pre_review() -> None:
    approval = WORKSPACE.split("async function approveAndDownload", 1)[1].split(
        "async function recordOtherDecision", 1
    )[0]
    assert "if (!canonicalApprovalReady)" in approval
    assert "if (!exactEditionDownloaded)" in approval
    assert 'submitDecision("approved")' in approval
    submit = WORKSPACE.split("async function submitDecision", 1)[1].split(
        "async function prepareLocalizedEdition", 1
    )[0]
    assert "review_authorized: true" in submit
    assert "reviewer: reviewer.trim()" in submit
    assert "reviewer_role: reviewerRole.trim()" in submit


def test_owner_test_is_one_tap_on_ios_without_bottom_fallback_box() -> None:
    assert '"Generate owner test final PDF"' in HANDOFF
    assert '"Generar PDF final de prueba del propietario"' in HANDOFF
    assert 'window.open("about:blank", "nico-comprehensive-pdf")' in HANDOFF
    assert "targetWindow.location.replace(href)" in HANDOFF
    assert "data-final-review-pdf-handoff" not in HANDOFF
    assert "PDF is ready" not in HANDOFF
    assert "Open PDF" not in HANDOFF


def test_obsolete_readiness_wrapper_is_not_wired_into_page() -> None:
    assert "FinalReviewReadinessBoundary" not in PAGE
    assert "<ComprehensiveFinalReviewWorkspace />" in PAGE


def test_structured_evidence_spacebar_fix_is_preserved() -> None:
    editor = STRATEGIC.split("export function evidenceLines", 1)[1].split(
        "export function moduleCompleteness", 1
    )[0]
    assert ".split(/\\r?\\n/)" in editor
    assert ".map((item) => item.trim())" not in editor
    assert ".filter(Boolean)" not in editor
    assert ".slice(0, 100)" in editor
