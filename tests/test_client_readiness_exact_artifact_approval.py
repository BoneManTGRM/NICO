from __future__ import annotations

from copy import deepcopy

from nico.client_readiness_exact_artifact_approval_v2 import (
    build_approval_subject,
    evaluate_exact_artifact_approval,
    validate_exact_artifact_approval,
)


SHA = "a" * 40
DIGEST = "b" * 64
_DETACHED_DIGESTS = ("c" * 64, "d" * 64, "e" * 64, "f" * 64, "1" * 64)


def _identity() -> dict:
    return {
        "repository": "BoneManTGRM/NICO",
        "commit_sha": SHA,
        "run_id": "comprun_exact",
        "evidence_ledger_id": "ledger_exact",
    }


def _report_digests() -> dict:
    return {
        name: {"sha256": DIGEST, "size_bytes": index + 100}
        for index, name in enumerate(("markdown", "html", "pdf", "json"))
    }


def _detached_artifacts() -> dict:
    return {
        name: {
            "filename": f"{name}.json" if name.endswith("json") or name == "evidence_manifest" else f"{name}.csv",
            "sha256": _DETACHED_DIGESTS[index],
            "size_bytes": 500 + index,
        }
        for index, name in enumerate(
            (
                "findings_csv",
                "evidence_csv",
                "candidate_register_json",
                "remediation_backlog_json",
                "evidence_manifest",
            )
        )
    }


def _gates() -> dict:
    return {
        "candidate_triage": {"status": "passed", "register_digest": "1" * 64},
        "operational_proof": {"status": "passed", "proof_manifest_sha256": "2" * 64},
        "finding_disposition": {"status": "passed", "register_digest": "3" * 64},
        "client_evidence": {"status": "passed", "register_digest": "4" * 64},
        "cross_format_parity": {"status": "passed", "parity_digest": "5" * 64},
    }


def _receipt(subject: dict) -> dict:
    return {
        "reviewer": {
            "identity": "authorized-reviewer",
            "role": "client delivery approver",
            "authorized": True,
            "authorization_basis": "engagement approval matrix",
            "recorded_at": "2026-08-05T18:30:00Z",
        },
        "decision": "approved",
        "decision_reason": "The exact evidence-bound package and limitations were reviewed.",
        "approved_subject_sha256": subject["approval_subject_sha256"],
        "residual_risk_acceptance": {
            "identity": "authorized-risk-owner",
            "role": "residual risk owner",
            "authorized": True,
            "authorization_basis": "client risk authority",
            "recorded_at": "2026-08-05T18:30:00Z",
            "scope": "Exact run and exact artifact digest set",
            "statement": "Residual risks and retained limitations are accepted for this exact package.",
        },
    }


def test_complete_exact_subject_and_authorized_receipt_allow_delivery() -> None:
    subject = build_approval_subject(
        identity=_identity(),
        report_artifact_digests=_report_digests(),
        artifact_manifest=_detached_artifacts(),
        readiness_gates=_gates(),
    )
    approval = evaluate_exact_artifact_approval(subject, _receipt(subject))
    validation = validate_exact_artifact_approval(approval)

    assert subject["status"] == "ready_for_human_approval"
    assert set(subject["artifacts"]) == {
        "markdown", "html", "pdf", "json", "findings_csv", "evidence_csv",
        "candidate_register_json", "remediation_backlog_json", "evidence_manifest",
    }
    assert approval["status"] == "approved"
    assert approval["client_delivery_allowed"] is True
    assert validation["status"] == "approved"


def test_missing_detached_artifact_or_failed_gate_blocks_subject() -> None:
    artifacts = _detached_artifacts()
    artifacts.pop("evidence_manifest")
    gates = _gates()
    gates["candidate_triage"]["status"] = "blocked"

    subject = build_approval_subject(
        identity=_identity(),
        report_artifact_digests=_report_digests(),
        artifact_manifest=artifacts,
        readiness_gates=gates,
    )

    assert subject["status"] == "blocked"
    errors = " ".join(subject["validation_errors"])
    assert "evidence_manifest" in errors
    assert "candidate_triage gate has not passed" in errors


def test_unauthorized_reviewer_or_risk_owner_cannot_approve() -> None:
    subject = build_approval_subject(
        identity=_identity(),
        report_artifact_digests=_report_digests(),
        artifact_manifest=_detached_artifacts(),
        readiness_gates=_gates(),
    )
    receipt = _receipt(subject)
    receipt["reviewer"]["authorized"] = False
    receipt["residual_risk_acceptance"]["authorized"] = False

    approval = evaluate_exact_artifact_approval(subject, receipt)

    assert approval["status"] == "blocked"
    assert approval["client_delivery_allowed"] is False
    errors = " ".join(approval["validation_errors"])
    assert "reviewer.authorized must be true" in errors
    assert "residual_risk_acceptance.authorized must be true" in errors


def test_receipt_for_stale_subject_digest_is_rejected() -> None:
    subject = build_approval_subject(
        identity=_identity(),
        report_artifact_digests=_report_digests(),
        artifact_manifest=_detached_artifacts(),
        readiness_gates=_gates(),
    )
    receipt = _receipt(subject)
    receipt["approved_subject_sha256"] = "0" * 64

    approval = evaluate_exact_artifact_approval(subject, receipt)

    assert approval["status"] == "blocked"
    assert "does not match the exact current subject" in " ".join(approval["validation_errors"])


def test_artifact_or_gate_change_invalidates_prior_approval() -> None:
    subject = build_approval_subject(
        identity=_identity(),
        report_artifact_digests=_report_digests(),
        artifact_manifest=_detached_artifacts(),
        readiness_gates=_gates(),
    )
    approval = evaluate_exact_artifact_approval(subject, _receipt(subject))
    tampered = deepcopy(approval)
    tampered["approval_subject"]["artifacts"]["findings_csv"]["sha256"] = "f" * 64

    validation = validate_exact_artifact_approval(tampered)

    assert validation["status"] == "blocked"
    assert "approval subject digest is invalid" in " ".join(validation["validation_errors"])


def test_caller_controlled_delivery_flag_cannot_bypass_receipt_validation() -> None:
    subject = build_approval_subject(
        identity=_identity(),
        report_artifact_digests=_report_digests(),
        artifact_manifest=_detached_artifacts(),
        readiness_gates=_gates(),
    )
    receipt = _receipt(subject)
    receipt["reviewer"]["authorized"] = False
    approval = evaluate_exact_artifact_approval(subject, receipt)
    approval["client_delivery_allowed"] = True
    approval["approved_final"] = True

    validation = validate_exact_artifact_approval(approval)

    assert validation["status"] == "blocked"
    assert "authorized human approval is not valid" in " ".join(validation["validation_errors"])
