from nico.client_job_mode import build_client_job_package, product_artifact_findings, quote_facts


def test_quote_facts_detects_express_scope_and_payment_terms():
    facts = quote_facts("Express Technical Health Assessment en 2 semanas por $4,500.00 + IVA. 50% al inicio y 50% a la entrega. Acceso read-only a repositorios y CI/CD.")
    assert facts["service_detected"] == "Express Technical Health Assessment"
    assert facts["timeline"] == "2 weeks"
    assert facts["price"] == "$4,500.00 USD + IVA"
    assert "Read-only repository access" in facts["client_responsibilities"]
    assert "CI/CD configuration and logs" in facts["client_responsibilities"]


def test_product_artifact_findings_detects_provider_gate():
    findings = product_artifact_findings("No verified picks. Current provider gate. Provider not matched. Data unavailable. Research only. No live team snapshot. No verified lineup update returned.")
    ids = {item["id"] for item in findings}
    assert "no_verified_picks" in ids
    assert "current_provider_gate" in ids
    assert "research_only" in ids
    assert "snapshot_missing" in ids
    assert "lineup_injury_unverified" in ids


def test_client_job_package_marks_human_review_and_deliverables():
    package = build_client_job_package({
        "client_name": "Client",
        "project_name": "Project",
        "repository": "owner/repo",
        "quote_text": "Express Technical Health Assessment $4,500.00 + IVA 2 weeks 50%",
        "product_evidence_text": "No verified picks current provider gate research only data unavailable",
        "assessment": {"status": "complete", "evidence_readiness": {"scanner_worker_attached": True}, "sections": [{"id": "code_audit"}]},
    })
    assert package["status"] == "ok"
    assert package["human_review_required"] is True
    assert package["delivery_verdict"] == "draft_ready_for_human_review"
    assert package["product_artifact_findings"]
    deliverables = {item["deliverable"]: item["status"] for item in package["deliverable_checklist"]}
    assert deliverables["Code audit"] == "complete_with_review"
    assert deliverables["Client-ready package"] == "human_review_required"
