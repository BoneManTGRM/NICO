from pathlib import Path


WORKSPACE = Path(
    "apps/web/app/operations/final-review/ComprehensiveFinalReviewWorkspace.tsx"
).read_text(encoding="utf-8")
HANDOFF = Path(
    "apps/web/app/operations/final-review/FinalReviewDownloadHandoff.tsx"
).read_text(encoding="utf-8")


def function_body(name: str, next_name: str) -> str:
    return WORKSPACE.split(f"async function {name}", 1)[1].split(
        f"async function {next_name}", 1
    )[0]


def test_final_report_download_is_one_normal_path_independent_of_reviewer_metadata() -> None:
    report_download = function_body("downloadFinalReport", "approveExactReport")
    assert "downloadExactPdf(result" in report_download
    assert "canonicalApprovalReady" not in report_download
    assert "confirmed" not in report_download
    assert "submitDecision" not in report_download
    assert "reviewUrl()" not in report_download
    assert "deliveryAuthorizationUrl" not in report_download
    assert "OWNER-TEST-NON-DELIVERABLE" not in WORKSPACE
    assert "ownerTest" not in WORKSPACE


def test_human_approval_is_separate_and_preserves_exact_artifact_gate() -> None:
    approval = function_body("approveExactReport", "recordOtherDecision")
    assert "canonicalApprovalReady" in approval
    assert "confirmed" in approval
    assert "exactEditionDownloaded" in approval
    assert 'submitDecision("approved")' in approval
    assert "expected_artifact_identity: reviewArtifactIdentity" in WORKSPACE


def test_report_action_does_not_become_more_restrictive_when_reviewer_is_supplied() -> None:
    assert "onClick={downloadFinalReport}>{copy.downloadFinalReport}</button>" in WORKSPACE
    assert "onClick={approveExactReport}>{copy.approveExactReport}</button>" in WORKSPACE
    assert "canonicalApprovalReady ? copy.approveDownload" not in WORKSPACE
    assert "canonicalApprovalReady ? copy.recording" not in WORKSPACE


def test_report_action_does_not_require_human_review_acknowledgement() -> None:
    assert (
        'disabled={loading || !currentReviewPdfDigest} onClick={downloadFinalReport}'
        in WORKSPACE
    )
    assert (
        'disabled={loading || !confirmed || !exactEditionDownloaded} onClick={approveExactReport}'
        in WORKSPACE
    )


def test_client_delivery_remains_separately_protected() -> None:
    delivery = function_body("authorizeClientDelivery", "downloadPackage")
    assert "canonicalApprovalReady" in delivery
    assert "approvalCompleted" in delivery
    assert "deliveryConfirmed" in delivery
    assert "downloadedArtifactDigest !== currentReviewPdfDigest" in delivery
    assert "delivery_authorized: true" in delivery


def test_report_download_preserves_exact_pdf_integrity_verification() -> None:
    verifier = WORKSPACE.split("async function downloadBase64Pdf", 1)[1].split(
        "async function responseError", 1
    )[0]
    assert 'String.fromCharCode(...bytes.slice(0, 4)) !== "%PDF"' in verifier
    assert 'window.crypto.subtle.digest("SHA-256", buffer)' in WORKSPACE
    assert "actualSha256 !== expectedSha256.toLowerCase()" in verifier


def test_ios_handoff_recognizes_normal_final_report_action_without_owner_test_path() -> None:
    assert '"Download final assessment PDF"' in HANDOFF
    assert '"Descargar PDF final de la evaluación"' in HANDOFF
    assert '"Approve exact downloaded report"' in HANDOFF
    assert '"Aprobar informe exacto descargado"' in HANDOFF
    assert "owner test" not in HANDOFF.lower()
    assert 'window.open("about:blank", "nico-comprehensive-pdf")' in HANDOFF
    assert "targetWindow.location.replace(href)" in HANDOFF
