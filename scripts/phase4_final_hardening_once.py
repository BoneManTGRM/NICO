from __future__ import annotations

from pathlib import Path

CONTRACT = Path("nico/comprehensive_client_delivery_contract_v1.py")
TESTS = Path("tests/test_phase4_client_delivery_contract_v1.py")


def replace_function(text: str, name: str, next_name: str, replacement: str) -> str:
    start = text.index(f"def {name}(")
    end = text.index(f"\n\ndef {next_name}", start)
    return text[:start] + replacement.rstrip() + text[end:]


def patch_contract() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    if "import io\n" not in text:
        text = text.replace("import hashlib\nimport json\n", "import hashlib\nimport io\nimport json\n", 1)
    if "from pypdf import PdfReader\n" not in text:
        text = text.replace("from typing import Any\n", "from typing import Any\n\nfrom pypdf import PdfReader\n", 1)

    automation = '_AUTOMATION = {"automation", "automated reviewer", "bot", "nico automation", "system", "system reviewer"}\n'
    if "_AUTHORIZED_REVIEWER_ROLES" not in text:
        text = text.replace(
            automation,
            automation
            + '\n_AUTHORIZED_REVIEWER_ROLES = {\n'
            + '    "application security engineer",\n'
            + '    "application security specialist",\n'
            + '    "cybersecurity analyst",\n'
            + '    "cybersecurity consultant",\n'
            + '    "cybersecurity reviewer",\n'
            + '    "cybersecurity specialist",\n'
            + '    "lead cybersecurity specialist",\n'
            + '    "penetration tester",\n'
            + '    "principal security engineer",\n'
            + '    "security analyst",\n'
            + '    "security consultant",\n'
            + '    "security engineer",\n'
            + '    "security reviewer",\n'
            + '    "security specialist",\n'
            + '    "senior application security engineer",\n'
            + '    "senior cybersecurity specialist",\n'
            + '    "senior security engineer",\n'
            + '}\n_AUTHORIZED_REVIEWER_BASES = {\n'
            + '    "protected_admin_write_and_explicit_review_authorization",\n'
            + '}\n',
            1,
        )

    artifact = '''def _decode_structurally_valid_pdf(value: Any) -> bytes:
    try:
        pdf = base64.b64decode(_text(value), validate=True)
        reader = PdfReader(io.BytesIO(pdf), strict=False)
        if len(reader.pages) < 1:
            return b""
        return pdf
    except Exception:
        return b""


def artifact_digests(record: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    package = _report(record)
    values: dict[str, Any] = {
        "markdown": package.get("markdown"),
        "html": package.get("html"),
        "json": package.get("json"),
        "pdf": _decode_structurally_valid_pdf(package.get("pdf_base64")),
    }
    for source, name in (
        ("findings_csv", "findings_csv"),
        ("evidence_csv", "evidence_csv"),
        ("jira_csv", "remediation_csv"),
        ("candidate_register_csv", "candidate_register_csv"),
    ):
        values[name] = package.get(source)
    output: dict[str, dict[str, Any]] = {}
    for name, value in values.items():
        if value in (None, "", b""):
            continue
        encoded = value if isinstance(value, bytes) else value.encode() if isinstance(value, str) else _canonical_bytes(value)
        output[name] = {"sha256": hashlib.sha256(encoded).hexdigest(), "size_bytes": len(encoded)}
    return output
'''
    text = replace_function(text, "artifact_digests", "_identity_scope", artifact)

    scanner = '''def _scanner_contract(record: Mapping[str, Any]) -> dict[str, Any]:
    contract = _mapping(record.get("scanner_execution_contract"))
    register = _register(record)
    executions = contract.get("executions")
    if not isinstance(executions, list):
        executions = register.get("scanner_executions")
    if not isinstance(executions, list):
        executions = _mapping(_stages(record).get("dependency_security_static_analysis")).get("scanner_executions")

    def scanner_name(value: Any) -> str:
        if isinstance(value, Mapping):
            value = value.get("scanner") or value.get("name")
        return _text(value)

    declared = contract.get("required_scanners")
    _require(isinstance(declared, list) and bool(declared), "required_scanner_set_missing")
    required = {scanner_name(value).casefold() for value in declared if scanner_name(value)}
    _require(bool(required), "required_scanner_set_missing")
    _require(_text(contract.get("support_status") or "supported").casefold() in {"supported", "applicable"}, "unsupported_ecosystem_not_assessed")
    _require(isinstance(executions, list) and bool(executions), "required_scanner_execution_missing")

    failed: list[str] = []
    unsupported: list[str] = []
    executed: set[str] = set()
    for item in executions:
        if not isinstance(item, Mapping):
            failed.append("malformed")
            continue
        name = scanner_name(item) or "unknown"
        if name != "unknown":
            executed.add(name.casefold())
        support = _text(item.get("support_status") or "supported").casefold()
        status = _text(item.get("status")).casefold()
        if support not in {"supported", "applicable"}:
            unsupported.append(name)
        elif status not in {"completed", "passed", "success", "succeeded", "not_applicable"}:
            failed.append(name)
        _require(bool(_text(item.get("artifact_sha256") or item.get("manifest_sha256"))), "scanner_artifact_digest_missing", name)
    missing = sorted(required - executed)
    _require(not missing, "required_scanner_execution_missing", ",".join(missing))
    _require(not unsupported, "unsupported_ecosystem_not_assessed", ",".join(unsupported))
    _require(not failed, "required_scanner_execution_failed", ",".join(failed))
    return {
        "required_scanner_count": len(required),
        "scanner_execution_count": len(executions),
        "scanner_artifacts_retained": True,
    }
'''
    text = replace_function(text, "_scanner_contract", "_candidate_contract", scanner)

    candidate = '''def _candidate_contract(record: Mapping[str, Any]) -> dict[str, Any]:
    register = _register(record)
    findings = register.get("findings")
    _require(isinstance(findings, list), "malformed_candidate_register")
    try:
        declared = int(register.get("candidate_record_count"))
    except (TypeError, ValueError):
        declared = -1
    _require(declared == len(findings), "candidate_register_count_mismatch")
    ledger = _mapping(record.get("review_work_ledger"))
    dispositions = _mapping(ledger.get("dispositions"))
    pending_individual: list[str] = []
    candidate_ids: set[str] = set()
    triaged = 0
    for row in findings:
        _require(isinstance(row, Mapping), "malformed_candidate_register")
        candidate_id = _text(row.get("candidate_id"))
        _require(bool(candidate_id), "candidate_identity_missing")
        _require(candidate_id not in candidate_ids, "duplicate_candidate_identity", candidate_id)
        candidate_ids.add(candidate_id)
        lineage = _mapping(row.get("lineage"))
        _require(bool(_text(row.get("candidate_lineage_version") or lineage.get("version"))) and bool(_text(row.get("lineage_status") or lineage.get("status"))), "stale_candidate_lineage", candidate_id)
        triage = _mapping(row.get("technical_triage"))
        verdict = _text(triage.get("verdict") or row.get("technical_triage_verdict"))
        confidence = triage.get("confidence", row.get("technical_triage_confidence"))
        _require(bool(verdict) and confidence not in (None, ""), "incomplete_required_technical_triage", candidate_id)
        triaged += 1
        has_disposition = candidate_id in dispositions or isinstance(row.get("human_disposition"), Mapping)
        if row.get("review_requires_individual_attention") is True and not has_disposition:
            pending_individual.append(candidate_id)
    _require(not pending_individual, "mandatory_individual_review_unresolved", ",".join(pending_individual))
    disposition_ids = {_text(candidate_id) for candidate_id in dispositions if _text(candidate_id)}
    missing = sorted(candidate_ids - disposition_ids)
    unknown = sorted(disposition_ids - candidate_ids)
    _require(not missing, "candidate_dispositions_incomplete", ",".join(missing))
    _require(not unknown, "candidate_disposition_unknown_candidate", ",".join(unknown))
    malformed = sorted(
        candidate_id
        for candidate_id in candidate_ids
        if not isinstance(dispositions.get(candidate_id), Mapping)
        or not _text(_mapping(dispositions.get(candidate_id)).get("decision"))
    )
    _require(not malformed, "candidate_disposition_malformed", ",".join(malformed))
    return {
        "total_candidates": len(findings),
        "technical_triage_completed": triaged,
        "mandatory_individual_review_pending": len(pending_individual),
        "candidate_dispositions_reconciled": True,
    }
'''
    text = replace_function(text, "_candidate_contract", "_review_contract", candidate)

    artifact_contract = '''def _artifact_contract(record: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    package = _report(record)
    _require(_text(package.get("product_name") or package.get("report_product") or PRODUCT_NAME) == PRODUCT_NAME, "alternate_report_product_rejected")
    _require(_text(package.get("report_kind") or REPORT_KIND) == REPORT_KIND, "alternate_report_product_rejected")
    _require(_text(package.get("package_classification") or CLIENT_FINAL_CLASSIFICATION) == CLIENT_FINAL_CLASSIFICATION, "internal_or_test_package_presented_as_client_final")
    _require(package.get("one_client_report", True) is True and int(package.get("client_pdf_count") or 1) == 1, "one_comprehensive_report_required")
    digests = artifact_digests(record)
    for name in _REQUIRED_ARTIFACTS:
        if name == "pdf" and name not in digests and package.get("pdf_base64"):
            raise ClientDeliveryContractError("pdf_artifact_invalid")
        _require(name in digests, "required_final_artifact_missing", name)
    return digests
'''
    text = replace_function(text, "_artifact_contract", "operational_metrics", artifact_contract)

    reviewer = '''def reviewer_binding(
    *,
    reviewer: str,
    reviewer_role: str,
    decision: str,
    decided_at: str,
    decision_reason: str,
    authorization_basis: str = "protected_admin_write_and_explicit_review_authorization",
) -> dict[str, Any]:
    reviewer = _text(reviewer)
    role = _text(reviewer_role)
    decision = _text(decision).casefold()
    normalized_role = " ".join(role.casefold().split())
    normalized_basis = _text(authorization_basis)
    _require(bool(reviewer), "missing_reviewer_identity")
    _require(reviewer.casefold() not in _AUTOMATION, "automation_cannot_create_final_human_approval")
    _require(bool(role), "missing_reviewer_role")
    _require(normalized_role in _AUTHORIZED_REVIEWER_ROLES, "reviewer_role_not_authorized")
    _require(decision in {"approved", "rejected", "request_more_evidence"}, "invalid_review_decision")
    _require(bool(_text(decided_at)), "missing_review_timestamp")
    _require(bool(_text(decision_reason)), "reviewer_notes_required")
    _require(normalized_basis in _AUTHORIZED_REVIEWER_BASES, "reviewer_authorization_basis_not_authorized")
    payload = {
        "reviewer_identity": reviewer,
        "reviewer_role": role,
        "authorization_basis": normalized_basis,
        "review_decision": decision,
        "review_timestamp": _text(decided_at),
        "residual_risk_decision": "accepted_with_recorded_reason" if decision == "approved" else "not_accepted",
        "reviewer_notes": _text(decision_reason),
        "reviewer_session_requirement": "not_applicable_protected_admin_token_boundary",
        "human_action_required": True,
        "automation_may_not_approve": True,
    }
    payload["approval_record_id"] = "approval_" + canonical_sha256(payload)[:24]
    return payload
'''
    text = replace_function(text, "reviewer_binding", "build_approval_receipt", reviewer)
    CONTRACT.write_text(text, encoding="utf-8")


def patch_tests() -> None:
    text = TESTS.read_text(encoding="utf-8")
    if "from io import BytesIO\n" not in text:
        text = text.replace("from copy import deepcopy\n", "from copy import deepcopy\nfrom io import BytesIO\n", 1)
    if "from pypdf import PdfWriter\n" not in text:
        text = text.replace("import pytest\n", "import pytest\nfrom pypdf import PdfWriter\n", 1)
    if "def _valid_pdf_bytes()" not in text:
        text = text.replace(
            '\n\ndef _record(ecosystem: str = "python") -> dict:\n',
            '\n\ndef _valid_pdf_bytes() -> bytes:\n'
            '    buffer = BytesIO()\n'
            '    writer = PdfWriter()\n'
            '    writer.add_blank_page(width=612, height=792)\n'
            '    writer.write(buffer)\n'
            '    return buffer.getvalue()\n'
            '\n\ndef _record(ecosystem: str = "python") -> dict:\n',
            1,
        )
    text = text.replace(
        'base64.b64encode(b"%PDF-1.4\\nphase4-fixture\\n%%EOF").decode("ascii")',
        'base64.b64encode(_valid_pdf_bytes()).decode("ascii")',
        1,
    )
    if "test_every_declared_required_scanner_must_have_an_execution" not in text:
        text += '''


def test_every_declared_required_scanner_must_have_an_execution() -> None:
    record = _record()
    record["scanner_execution_contract"]["required_scanners"].append("semgrep")
    result = validate_full_lifecycle(record)
    assert result["status"] == "blocked"
    assert "required_scanner_execution_missing" in result["validation_errors"]


def test_required_scanner_set_is_mandatory() -> None:
    record = _record()
    record["scanner_execution_contract"].pop("required_scanners")
    result = validate_full_lifecycle(record)
    assert result["status"] == "blocked"
    assert "required_scanner_set_missing" in result["validation_errors"]


def test_every_canonical_candidate_requires_an_exact_ledger_disposition() -> None:
    record = _record()
    candidate = record["stage_results"]["final_comprehensive_report_generation"]["report_package"]["json"]["assessment"]["canonical_scanner_finding_register"]["findings"][0]
    candidate["review_requires_individual_attention"] = False
    candidate["grouped_review_eligible"] = True
    candidate.pop("human_disposition")
    record["review_work_ledger"]["dispositions"].clear()
    result = validate_full_lifecycle(record)
    assert result["status"] == "blocked"
    assert "candidate_dispositions_incomplete" in result["validation_errors"]


def test_unknown_candidate_disposition_fails_closed() -> None:
    record = _record()
    record["review_work_ledger"]["dispositions"]["candidate-not-in-register"] = {
        "decision": "confirmed_material",
        "reviewer": "Alice Security",
        "reviewer_role": "Cybersecurity specialist",
    }
    result = validate_full_lifecycle(record)
    assert result["status"] == "blocked"
    assert "candidate_disposition_unknown_candidate" in result["validation_errors"]


def test_deceptive_security_display_title_is_not_an_authorized_role() -> None:
    with pytest.raises(ClientDeliveryContractError, match="reviewer_role_not_authorized"):
        build_approval_receipt(
            _record(),
            _manifest(_record()),
            reviewer="Alice Example",
            reviewer_role="Security sales representative",
            decision="approved",
            decided_at="2026-08-21T15:00:00+00:00",
            decision_reason="Attempted approval with a non-specialist role.",
        )


def test_self_asserted_authorization_basis_is_rejected() -> None:
    record = _record()
    with pytest.raises(ClientDeliveryContractError, match="reviewer_authorization_basis_not_authorized"):
        build_approval_receipt(
            record,
            _manifest(record),
            reviewer="Alice Security",
            reviewer_role="Cybersecurity specialist",
            decision="approved",
            decided_at="2026-08-21T15:00:00+00:00",
            decision_reason="Attempted approval without the protected authority.",
            authorization_basis="self_asserted",
        )


def test_base64_bytes_that_are_not_a_parseable_pdf_fail_closed() -> None:
    record = _record()
    package = record["stage_results"]["final_comprehensive_report_generation"]["report_package"]
    package["pdf_base64"] = base64.b64encode(b"not a pdf").decode("ascii")
    result = validate_full_lifecycle(record)
    assert result["status"] == "blocked"
    assert "pdf_artifact_invalid" in result["validation_errors"]
'''
    TESTS.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_contract()
    patch_tests()
