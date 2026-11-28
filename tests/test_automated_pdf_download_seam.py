"""Offline proof of exact native-language PDF reuse, not an eligibility or route test."""
from __future__ import annotations

import base64
import hashlib
import io
import zipfile
from copy import deepcopy

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico import comprehensive_automated_delivery_v1 as delivery
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_review_decision_v1 import review_artifact_identity
from nico.comprehensive_same_run_locale_report_v1 import build_same_run_locale_pdf_response


TIMESTAMP = "2026-08-21T16:00:00Z"
LABELS = {"en": ("Technical evidence", "Measured results"),
          "es-MX": ("Evidencia técnica", "Resultados medidos")}


def _fixture(locale):
    identity = {"run_id": "comprun_synthetic_native", "repository": "Example/Fixture",
                "commit_sha": "a" * 40, "evidence_ledger_id": "ledger_synthetic_native",
                "report_language": locale}
    canonical = {"report_id": "synthetic_native", "identity": identity, "assessment": {}}
    buffer = io.BytesIO()
    composer = canvas.Canvas(buffer, invariant=1)
    for index, title in enumerate(LABELS[locale]):
        composer.setPageSize((595 + index * 20, 842 - index * 32))
        composer.rect(25, 30, 200, 20)
        composer.bookmarkPage(f"fixture-{index}")
        composer.addOutlineEntry(title, f"fixture-{index}", level=index)
        if index == 0:
            composer.linkRect("", "fixture-1", (25, 30, 225, 50))
        composer.drawString(37, 600, title)
        composer.showPage()
    composer.save()
    pdf = buffer.getvalue()
    source = {"report_id": canonical["report_id"], "json": canonical,
              "canonical_truth_sha256": canonical_sha256(canonical),
              "pdf_base64": base64.b64encode(pdf).decode(),
              "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
              "markdown": "# Synthetic report", "html": "<p>Synthetic report</p>"}
    record = {"identity": identity, "status": "review_required", "terminal": True,
              "revision": 7, "human_review_completed": False,
              "client_delivery_allowed": False, "reports": source}
    status = {**identity, "record": record, "reports": source, "terminal": True}
    return record, status


@pytest.mark.parametrize("locale", ["en", "es-MX"])
def test_one_exact_pdf_for_authorized_zip_and_direct_response_candidate(locale, monkeypatch):
    record, status = _fixture(locale)
    original = deepcopy(record)
    identity = review_artifact_identity(record)
    pending = build_same_run_locale_pdf_response(status, locale)
    assert pending.headers["x-nico-report-language"] == locale
    assert pending.headers["x-nico-approval-status"] == "pending_human_approval"
    assert pending.headers["x-nico-client-delivery-allowed"] == "false"
    prepared = delivery._prepare_automated_delivery_pdf(
        record, expected_artifact_identity=identity, authorized_at=TIMESTAMP,
    )
    # If future attachment plumbing reuses this sealed artifact, ZIP assembly may
    # consume it without asking the report renderer to build an independent copy.
    monkeypatch.setattr(delivery, "_prepare_automated_delivery_pdf", lambda *_a, **_kw: prepared)
    archive = delivery.build_automated_delivery_package(
        record, expected_artifact_identity=identity, authorized_at=TIMESTAMP,
    )
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(archive["zip_base64"]))) as bundle:
        retained_bytes = bundle.read("01_nico_comprehensive_report.pdf")
    assert retained_bytes == prepared.pdf_bytes
    row = next(row for row in archive["manifest"]["artifacts"] if row["path"].endswith(".pdf"))
    assert row["sha256"] == hashlib.sha256(prepared.pdf_bytes).hexdigest()
    assert archive["authorization"]["source_pdf_sha256"] == hashlib.sha256(pending.body).hexdigest()
    assert archive["authorization"]["source_report_artifact_digest"] == identity["report_artifact_digest"]
    assert archive["authorization"]["human_reviewed"] is False
    assert archive["authorization"]["security_certification"] is False
    assert archive["client_delivery_allowed"] is True
    source = PdfReader(io.BytesIO(pending.body))
    authorized = PdfReader(io.BytesIO(prepared.pdf_bytes))
    assert len(authorized.pages) == len(source.pages) + 1
    certificate = " ".join(authorized.pages[0].extract_text().split())
    if locale == "es-MX":
        assert "EVALUACIÓN TÉCNICA AUTOMATIZADA AUTORIZADA" in certificate
        assert "Certificado de autorización de entrega al cliente" in certificate
        assert "Ningún especialista humano en ciberseguridad revisó ni certificó este informe." in certificate
        assert "verificación lógica independiente" in certificate
        assert "Client Delivery Authorization Certificate" not in certificate
    else:
        assert "AUTHORIZED AUTOMATED TECHNICAL ASSESSMENT" in certificate
        assert "Client Delivery Authorization Certificate" in certificate
        assert "No human cybersecurity specialist reviewed or certified this report." in certificate
    assert identity["artifact_digests"]["pdf"]["sha256"] in certificate
    assert record["identity"]["commit_sha"] in certificate
    assert authorized.outline[0].title == LABELS[locale][0]
    assert authorized.outline[1][0].title == LABELS[locale][1]
    assert authorized.get_destination_page_number(authorized.outline[0]) == 1
    assert authorized.get_destination_page_number(authorized.outline[1][0]) == 2
    internal = authorized.pages[1]["/Annots"][0].get_object()["/Dest"]
    assert internal[0].idnum == authorized.pages[2].indirect_reference.idnum
    for i, page in enumerate(source.pages):
        after = authorized.pages[i + 1]
        assert tuple(page.mediabox) == tuple(after.mediabox)
        assert LABELS[locale][i] in after.extract_text()
        assert page.get_contents().get_data() == after.get_contents().get_data()
    assert record == original


@pytest.mark.parametrize("mutate", [lambda r: r.update(revision=8),
                                     lambda r: r["reports"].update(markdown="other edition"),
                                     lambda r: r.update(terminal=False),
                                     lambda r: r.update(client_delivery_allowed=True)])
def test_seam_cannot_prepare_stale_or_out_of_lifecycle_input(mutate, monkeypatch):
    record, _ = _fixture("es-MX")
    identity = review_artifact_identity(record)
    mutate(record)
    monkeypatch.setattr(delivery, "build_authorized_report_pdf",
                        lambda *_a, **_kw: pytest.fail("invalid source reached renderer"))
    with pytest.raises(ValueError, match="stale_review_artifact|automated_delivery_requires_"):
        delivery._prepare_automated_delivery_pdf(
            record, expected_artifact_identity=identity, authorized_at=TIMESTAMP,
        )


@pytest.mark.parametrize("boundary", ["identity_declaration", "package_declaration", "canonical_locale"])
def test_automated_certificate_rejects_inconsistent_retained_language(boundary, monkeypatch):
    record, _ = _fixture("es-MX")
    if boundary == "identity_declaration":
        record["identity"] = dict(record["identity"], report_language="en")
    elif boundary == "package_declaration":
        record["reports"]["locale"] = "en"
    else:
        record["reports"]["json"]["assessment"]["locale"] = "en"
    monkeypatch.setattr(delivery, "build_authorized_report_pdf",
                        lambda *_a, **_kw: pytest.fail("ambiguous locale reached renderer"))
    with pytest.raises(ValueError, match="report_language|retained_language"):
        delivery._prepare_automated_delivery_pdf(
            record, expected_artifact_identity=review_artifact_identity(record),
            authorized_at=TIMESTAMP,
        )


def test_untrusted_language_preference_does_not_translate_english_edition():
    record, _ = _fixture("en")
    record["report_language"] = "es-MX"  # cannot overrule native signed report identity
    prepared = delivery._prepare_automated_delivery_pdf(
        record, expected_artifact_identity=review_artifact_identity(record),
        authorized_at=TIMESTAMP,
    )
    certificate = PdfReader(io.BytesIO(prepared.pdf_bytes)).pages[0].extract_text()
    assert "Client Delivery Authorization Certificate" in certificate
    assert "Certificado de autorización" not in certificate


def test_human_certificate_is_byte_identical_even_for_es_mx_language_argument():
    from nico.comprehensive_authorized_report_v1 import build_authorized_report_pdf

    record, _ = _fixture("es-MX")
    source = base64.b64decode(record["reports"]["pdf_base64"])
    arguments = dict(
        identity=record["identity"],
        delivery_authorization={"authorized_at": TIMESTAMP, "authorizer_identity": "Synthetic reviewer"},
        source_pdf_sha256=hashlib.sha256(source).hexdigest(),
    )
    baseline = build_authorized_report_pdf(source, **arguments)
    assert build_authorized_report_pdf(source, report_language="es-MX", **arguments) == baseline
