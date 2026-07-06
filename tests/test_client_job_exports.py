from nico.client_job_mode import create_client_job_package, export_client_job_package, list_client_job_exports


def test_client_job_package_export_formats():
    package = create_client_job_package({
        "client_name": "Client",
        "project_name": "Project",
        "repository": "owner/repo",
        "quote_text": "Express Technical Health Assessment 2 weeks $4,500.00 + IVA 50%",
        "product_evidence_text": "No verified output. Data unavailable.",
        "assessment": {"sections": [{"id": "code_audit", "status": "yellow"}], "evidence_readiness": {"scanner_worker_attached": True}},
    })
    assert package["status"] == "ok"
    assert package["mode"] == "client_job_mode_v8"
    assert package["available_export_formats"] == ["html", "json", "markdown", "pdf"]

    json_export = export_client_job_package(package["job_id"], "json")
    markdown_export = export_client_job_package(package["job_id"], "markdown")
    html_export = export_client_job_package(package["job_id"], "html")
    pdf_export = export_client_job_package(package["job_id"], "pdf")

    assert json_export["status"] == "complete"
    assert markdown_export["mime_type"] == "text/markdown"
    assert "NICO Client Job Package" in markdown_export["content"]
    assert html_export["mime_type"] == "text/html"
    assert pdf_export["mime_type"] == "application/pdf"
    assert pdf_export["content_base64"]

    exports = list_client_job_exports(package["job_id"])
    assert len(exports["exports"]) >= 4


def test_client_job_unknown_export_format_is_unavailable():
    package = create_client_job_package({"client_name": "Client", "project_name": "Project"})
    result = export_client_job_package(package["job_id"], "docx")
    assert result["status"] == "unavailable"
    assert "json" in result["available_formats"]
