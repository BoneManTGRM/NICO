from __future__ import annotations

import base64
import io

from pypdf import PdfReader

from nico.comprehensive_engagement_metadata_v1 import (
    build_comprehensive_engagement_metadata,
)
from nico.comprehensive_report_worker_runtime_v90 import _report_identity
from nico.final_report_ship_closure_v94 import (
    build_ship_ready_report_package,
    install_final_report_ship_closure_v94,
)


CLIENT = "Cody Jenkins"
PROJECT = "NICO Audit"
CONTACT = "Cody Jenkins — Repository owner / project lead"
ACCESS = "Public GitHub repository via HTTPS/API — read-only access"
SCOPE = "BoneManTGRM/NICO — entire repository, current main branch."


def _metadata() -> dict:
    return build_comprehensive_engagement_metadata(
        client_name=CLIENT,
        project_name=PROJECT,
        human_evidence={
            "stakeholder_context": {
                "evidence": {
                    "primary_technical_contact": [CONTACT],
                    "access_method": [ACCESS],
                    "authorized_scope": [SCOPE],
                }
            }
        },
    )


def _context() -> dict[str, object]:
    return {
        "run_id": "comprun_ship_closure_v94",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_ship_closure_v94",
        "customer_id": "customer_ship_closure_v94",
        "project_id": "project_ship_closure_v94",
        "engagement_metadata": _metadata(),
        "human_evidence": {},
    }


def test_verified_durable_engagement_snapshot_reaches_detached_report_identity() -> None:
    install_final_report_ship_closure_v94()
    identity = _report_identity(_context())

    assert identity["customer_name"] == CLIENT
    assert identity["project_name"] == PROJECT
    assert identity["primary_technical_contact"] == CONTACT
    assert identity["access_method"] == ACCESS
    assert identity["authorized_scope"] == SCOPE
    assert identity["engagement_metadata_sha256"] == _metadata()["engagement_metadata_sha256"]


def test_tampered_durable_engagement_snapshot_is_not_projected() -> None:
    install_final_report_ship_closure_v94()
    context = _context()
    metadata = dict(context["engagement_metadata"])
    metadata["authorized_scope"] = "tampered scope"
    context["engagement_metadata"] = metadata

    identity = _report_identity(context)

    assert "customer_name" not in identity
    assert "project_name" not in identity
    assert "primary_technical_contact" not in identity
    assert "access_method" not in identity
    assert "authorized_scope" not in identity
    assert "engagement_metadata_sha256" not in identity


def test_all_five_client_supplied_fields_reach_json_markdown_html_and_pdf() -> None:
    install_final_report_ship_closure_v94()
    identity = _report_identity(_context())
    package = build_ship_ready_report_package(identity=identity, stage_results={})

    assert package["status"] == "complete"
    report = package["report_package"]
    canonical_identity = report["json"]["identity"]
    for key, value in {
        "customer_name": CLIENT,
        "project_name": PROJECT,
        "primary_technical_contact": CONTACT,
        "access_method": ACCESS,
        "authorized_scope": SCOPE,
    }.items():
        assert canonical_identity[key] == value

    markdown = report["markdown"]
    assert f"Client display name: {CLIENT}" in markdown
    assert f"Project display name: {PROJECT}" in markdown
    assert f"Primary technical contact: {CONTACT}" in markdown
    assert f"Access method: {ACCESS}" in markdown
    assert f"Authorized scope: {SCOPE}" in markdown

    html = report["html"]
    assert CLIENT in html
    assert PROJECT in html
    assert CONTACT in html
    assert ACCESS in html
    assert SCOPE in html

    pdf = base64.b64decode(report["pdf_base64"])
    assert pdf.startswith(b"%PDF")
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    assert CLIENT in pdf_text
    assert PROJECT in pdf_text
    assert "Primary technical contact" in pdf_text
    assert "Access method" in pdf_text
    assert "Authorized scope" in pdf_text


def test_spanish_ship_guard_localizes_labels_but_preserves_client_values_verbatim() -> None:
    from nico import comprehensive_spanish_canonical_report_v87 as spanish

    manifest = install_final_report_ship_closure_v94()

    assert manifest["spanish_premium_localization_tree_passes"] == 1
    for field in (
        "customer_name",
        "project_name",
        "primary_technical_contact",
        "access_method",
        "authorized_scope",
    ):
        assert field in spanish._PROTECTED_FIELDS
        assert field in spanish._POST_RENDER_PROTECTED_FIELDS

    assert spanish._translate_presentation("Client display name") == "Nombre del cliente"
    assert spanish._translate_presentation("Project display name") == "Nombre del proyecto"
    assert spanish._translate_presentation("Primary technical contact") == "Contacto técnico principal"
    assert spanish._translate_presentation("Access method") == "Método de acceso"
    assert spanish._translate_presentation("Authorized scope") == "Alcance autorizado"

    supplied = {
        "customer_name": "North Star Client",
        "project_name": "English Project Name",
        "primary_technical_contact": "Jane Smith — Lead Engineer",
        "access_method": "Read-only HTTPS access",
        "authorized_scope": "Entire repository on current main branch",
    }
    localized = spanish._localize_tree(supplied, path=("identity",))
    assert localized == supplied
