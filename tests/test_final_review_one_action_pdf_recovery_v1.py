from pathlib import Path


WORKSPACE = Path("apps/web/app/operations/final-review/ComprehensiveFinalReviewWorkspace.tsx")
HYDRATION = Path("apps/web/app/operations/final-review/FinalReviewApprovedReportHydration.tsx")


def test_delivery_authorization_hydrates_exact_authorized_pdf_before_handoff() -> None:
    source = HYDRATION.read_text(encoding="utf-8")

    assert "DELIVERY_AUTHORIZATION_PATH" in source
    assert "payload.delivery_authorized === true" in source
    assert "payload.authorization_confirmed === true" in source
    assert "requireDeliveryAuthorization" in source
    assert "payload.client_delivery_allowed !== true" in source
    assert 'replace(/\\/(?:review|authorize-delivery)$/, "")' in source


def test_one_action_keeps_authorized_state_recoverable_until_pdf_is_presented() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")
    authorized_block = source.split("setResult(authorized);", 1)[1].split("setNotice(copy.approvedNotice);", 1)[0]

    assert "uncertainDecision.current = authorized;" in authorized_block
    assert "await downloadExactPdf(authorized)" in authorized_block
    assert authorized_block.index("uncertainDecision.current = authorized;") < authorized_block.index("await downloadExactPdf(authorized)")
    assert authorized_block.index("await downloadExactPdf(authorized)") < authorized_block.index("uncertainDecision.current = null;")


def test_persisted_authorization_retries_pdf_presentation_without_second_mutation() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")
    recovery = source.split("let recoveredPdf = false;", 1)[1].split(
        "const message = caught instanceof Error", 1
    )[0]

    assert "authorizationRecorded = persisted.client_delivery_allowed === true;" in recovery
    assert "if (authorizationRecorded)" in recovery
    assert "await downloadExactPdf(persisted)" in recovery
    assert "recoveredPdf = true;" in recovery
    assert "if (recoveredPdf) return;" in source
