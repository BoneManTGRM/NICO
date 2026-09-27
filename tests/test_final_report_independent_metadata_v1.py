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
    assert "approvalAuthorityReady" not in report_download
    assert "confirmed" not in report_download
    assert "submitDecision" not in report_download
    assert "reviewUrl()" not in report_download
    assert "deliveryAuthorizationUrl" not in report_download
    assert "OWNER-TEST-NON-DELIVERABLE" not in WORKSPACE
    assert "ownerTest" not in WORKSPACE


def test_human_approval_is_explicit_and_preserves_exact_artifact_gate() -> None:
    approval = function_body("approveExactReport", "recordOtherDecision")
    assert "!finalActionAuthorityReady" in approval
    assert "canonicalApprovalReady" not in approval
    assert "(!approvalCompleted && (!confirmed || !exactEditionDownloaded))" in approval
    assert 'submitDecision("approved")' in approval
    assert "expected_artifact_identity: reviewArtifactIdentity" in WORKSPACE
    assert "? canonicalApprovalReady : approvalAuthorityReady" in WORKSPACE


def test_operator_approval_metadata_remains_optional_and_authority_is_explicit() -> None:
    submit = function_body("submitDecision", "prepareLocalizedEdition")
    assert "const approvalMetadata = {reviewer, reviewerRole};" in submit
    assert "const reason = note;" in submit
    assert 'approval_kind: "operator_report"' in submit
    assert "exact_report_acknowledged: confirmed" in submit
    assert "approvalReviewerMetadata" not in WORKSPACE


def test_report_action_does_not_become_more_restrictive_when_reviewer_is_supplied() -> None:
    assert "onClick={downloadFinalReport}>{approvalCompleted ? copy.downloadApprovedReport : copy.downloadFinalReport}</button>" in WORKSPACE
    assert "onClick={approveExactReport}>{loading ? copy.recording : copy.approveExactReport}</button>" in WORKSPACE
    assert "canonicalApprovalReady ? copy.approveDownload" not in WORKSPACE
    assert "canonicalApprovalReady ? copy.recording" not in WORKSPACE


def test_report_download_does_not_require_human_review_acknowledgement() -> None:
    assert (
        'disabled={loading || !operatorReady || !finalPdfAvailable} onClick={downloadFinalReport}'
        in WORKSPACE
    )
    assert (
        'disabled={loading || !finalPdfAvailable || !finalActionAuthorityReady || !currentReviewPdfDigest || '
        '(!approvalCompleted && (!confirmed || !exactEditionDownloaded))} onClick={approveExactReport}'
        in WORKSPACE
    )


def test_client_delivery_keeps_exact_identity_protection_without_an_extra_user_step() -> None:
    approval = function_body("approveExactReport", "recordOtherDecision")
    assert 'delivery_kind: "operator_report"' in approval
    assert "delivery_authorized: true" in approval
    assert "authorization_confirmed: true" in approval
    assert "expected_artifact_identity: approvedArtifactIdentity" in approval
    assert "receipt.authorized_artifact_identity" in approval
    assert "reviewCertificateFrom(authorized).approval_certificate_sha256" in approval
    assert "authorized.client_delivery_allowed !== true" in approval
    assert "deliveryConfirmed" not in WORKSPACE
    assert "async function authorizeClientDelivery" not in WORKSPACE
    assert "approve it, and authorize client delivery" in WORKSPACE
    assert "lo apruebo y autorizo su entrega al cliente" in WORKSPACE


def test_operator_password_remains_required_for_approval_authority() -> None:
    assert "const operatorReady = Boolean(runId.trim() && adminToken.trim());" in WORKSPACE
    assert "const approvalAuthorityReady = operatorReady;" in WORKSPACE
    assert "approvalAuthorityReady = true" not in WORKSPACE
    assert 'adminToken.trim()' in WORKSPACE
    assert 'type="password"' in WORKSPACE


def test_report_download_preserves_exact_pdf_integrity_verification() -> None:
    verifier = WORKSPACE.split("async function downloadBase64Pdf", 1)[1].split(
        "async function responseError", 1
    )[0]
    assert 'String.fromCharCode(...bytes.slice(0, 4)) !== "%PDF"' in verifier
    assert 'window.crypto.subtle.digest("SHA-256", buffer)' in WORKSPACE
    assert "actualSha256 !== expectedSha256.toLowerCase()" in verifier
    assert "if (download) downloadBlob" in verifier


def test_ios_handoff_recognizes_normal_final_report_action_without_owner_test_path() -> None:
    assert '"Download final assessment PDF"' in HANDOFF
    assert '"Descargar PDF final de la evaluación"' in HANDOFF
    assert '"Approve exact downloaded report"' in HANDOFF
    assert '"Aprobar informe exacto descargado"' in HANDOFF
    assert "owner test" not in HANDOFF.lower()
    assert 'window.open("about:blank", "nico-comprehensive-pdf")' in HANDOFF
    assert "targetWindow.location.replace(href)" in HANDOFF


def test_final_action_is_visible_until_delivery_finishes_without_reviewer_metadata_gate() -> None:
    assert "!approvalCompleted && canonicalApprovalReady ? <button" not in WORKSPACE
    assert '!deliveryAllowed ? <button className={styles.approve}' in WORKSPACE
    assert 'aria-describedby="approval-next-step"' in WORKSPACE
    assert 'id="approval-next-step"' in WORKSPACE
    assert "const approvalNextStep = !approvalAuthorityReady" in WORKSPACE
    assert "copy.reviewDownloadRequired" in WORKSPACE
    assert "copy.approvalReady" in WORKSPACE
    assert 'optionalReviewerMetadata: "Reviewer name and role are optional for approval.' in WORKSPACE


def test_pending_download_does_not_claim_final_approval_in_filename() -> None:
    download = function_body("downloadFinalReport", "approveExactReport")
    assert "filenameOverride" not in WORKSPACE
    assert "FINAL-ASSESSMENT.pdf" not in WORKSPACE
    assert "downloadExactPdf(result);" in download
    assert 'safeFilename(String(exactReport.pdf_filename || ""), fallback)' in WORKSPACE


def test_final_action_reuses_approval_and_opens_only_the_authorized_pdf() -> None:
    approval = function_body("approveExactReport", "recordOtherDecision")
    assert "if (approvalInFlight.current) return;" in approval
    assert "approvalInFlight.current = true;" in approval
    assert "approvalInFlight.current = false;" in approval
    assert 'reuseApproval ? resumed : await submitDecision("approved")' in approval
    assert 'resumed = await reconcileFinalization(uncertainDecision.current)' in approval
    assert approval.index('reconcileFinalization(uncertainDecision.current)') < approval.index('await submitDecision("approved")')
    assert "copy.approvalDeliveryFailed" in approval
    assert "copy.pdfRetry" in approval
    assert approval.index("await downloadExactPdf(reviewed, false);") < approval.index("requestJson(deliveryAuthorizationUrl()")
    assert approval.index("authorized.client_delivery_allowed !== true") < approval.index("setResult(authorized)")
    assert approval.index("setResult(authorized)") < approval.index("await downloadExactPdf(authorized)")
    assert "downloadExactPdf(reviewed);" not in approval


def test_ios_pdf_action_marker_survives_localized_label_changes() -> None:
    assert 'data-nico-pdf-action="true"' in WORKSPACE
    assert 'button.dataset.nicoPdfAction !== "true"' in HANDOFF
    for label in (
        "Download report for review", "Download approved final PDF",
        "Approve and download final PDF", "Descargar informe para revisión",
        "Descargar PDF final aprobado", "Aprobar y descargar PDF final",
    ):
        assert label in HANDOFF
