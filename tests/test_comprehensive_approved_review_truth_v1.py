"""Generator regression only; synthetic fixture is not production approval evidence."""
import base64
import csv
import hashlib
import io

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from nico import comprehensive_approved_report_v1 as approved
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_review_report_truth_v1 import _review_pdf_page, _markdown_section, _html_section


def test_approved_edition_finalizes_review_truth_without_authorizing_delivery():
    truth = dict.fromkeys((
        'raw_scanner_candidates', 'technical_triage_completed', 'technical_triage_pending',
        'technical_triage_coverage_pct', 'not_actionable', 'needs_review', 'confirmed',
        'authorized_human_disposition_pending', 'authorized_human_disposition_completed',
        'confirmed_material_findings'), 0)
    truth.update(final_human_approval_status='pending', client_delivery_authorization_status='blocked',
                 reviewer_note='SYNTHETIC SOFTWARE-TEST INFORMATION — NOT PROFESSIONAL CYBERSECURITY JUDGMENT')
    body = io.BytesIO()
    pdf = canvas.Canvas(body, invariant=1)
    pdf.drawString(50, 750, 'Technical evidence: pending upstream remediation')
    pdf.save()
    writer = PdfWriter()
    for raw in (body.getvalue(), _review_pdf_page(truth)):
        writer.append(PdfReader(io.BytesIO(raw)))
    source = io.BytesIO()
    writer.write(source)
    raw = source.getvalue()
    package = {
        'json': {'identity': {'run_id': 'synthetic_generator_test', 'commit_sha': 'a'*40},
                 'human_review_truth': truth},
        'human_review_truth': truth,
        'phase2_review_truth_sha256': canonical_sha256(truth),
        **{key: 'id,note,final_human_approval_status,client_delivery_authorization_status\nc1,pending upstream remediation,pending,blocked\n' for key in ('findings_csv', 'evidence_csv', 'jira_csv', 'linear_csv')},
        'markdown': _markdown_section(truth), 'html': _html_section(truth),
        'pdf_base64': base64.b64encode(raw).decode(), 'pdf_sha256': hashlib.sha256(raw).hexdigest(),
    }
    for key in ('findings_csv', 'evidence_csv', 'jira_csv', 'linear_csv'):
        package[f'{key}_sha256'] = hashlib.sha256(package[key].encode('utf-8')).hexdigest()
    result = approved.build_approved_report_package(package, reviewer=truth['reviewer_note'],
        reviewer_role='SYNTHETIC SOFTWARE-TEST ROLE', decision_reason='SYNTHETIC GENERATOR TEST',
        decided_at='2026-09-09T00:00:00Z')
    for projected in (result['json']['human_review_truth'], result['human_review_truth']):
        assert projected['final_human_approval_status'] == 'approved'
        assert projected['client_delivery_authorization_status'] == 'certificate_controlled'
        assert projected['reviewer_note'] == truth['reviewer_note']
    assert 'Final human approval: APPROVED' in result['markdown']
    assert 'Final human approval:</strong> APPROVED' in result['html']
    assert 'Client-delivery authorization: Controlled separately' in result['markdown']
    assert 'Client-delivery authorization:</strong> Controlled separately' in result['html']
    pages = PdfReader(io.BytesIO(base64.b64decode(result['pdf_base64']))).pages
    text = pages[1].extract_text()
    assert 'Final human approval\nAPPROVED' in text
    assert 'Client-delivery authorization\nControlled separately' in text
    assert 'Technical evidence: pending upstream remediation' in pages[0].extract_text()
    for key in ('findings_csv', 'evidence_csv', 'jira_csv', 'linear_csv'):
        row = next(csv.DictReader(io.StringIO(result[key])))
        assert row['final_human_approval_status'] == 'approved'
        assert row['client_delivery_authorization_status'] == 'certificate_controlled'
        assert row['note'] == 'pending upstream remediation'
        assert result[f'{key}_sha256'] == hashlib.sha256(result[key].encode('utf-8')).hexdigest()
        assert result[f'{key}_sha256'] != package[f'{key}_sha256']
    assert result['phase2_review_truth_sha256'] == canonical_sha256(result['human_review_truth'])
    assert result['json']['approval_projection']['client_delivery_allowed'] is False
    assert result['json']['approval_projection']['delivery_authority'] == 'separate_certificate_required'
    assert result['client_delivery_allowed'] is False
    assert package['human_review_truth']['final_human_approval_status'] == 'pending'


def test_spanish_approved_labels_preserve_stakeholder_pending_evidence():
    # These lines are emitted by the actual es-MX renderer for revision 72.
    text = '\n'.join((
        'Estado de revisión: aprobación humana pendiente',
        'Estado de aprobación: aprobación humana pendiente',
        'Identidad del revisor: Pendiente',
        'Rol del revisor: Pendiente',
        'Autorización del revisor: Pendiente',
        'Decisión: Pendiente',
        'La aprobación humana autorizada sigue pendiente y la entrega al cliente permanece bloqueada.',
        'La entrega al cliente está bloqueada.',
        'Estado: Solo marco — pendiente de validación de las partes interesadas',
    ))
    result = approved._replace_finality_text(text)
    for stale in ('aprobación humana pendiente', 'del revisor: Pendiente',
                  'Decisión: Pendiente', 'humana autorizada sigue pendiente',
                  'cliente está bloqueada'):
        assert stale.casefold() not in result.casefold()
    assert 'Estado: Solo marco — pendiente de validación de las partes interesadas' in result
    escaped = '<li>&lt;span data-nico-client-literal=&quot;true&quot;&gt;Estado de revisión: aprobación humana pendiente&lt;/span&gt;</li>'
    assert 'aprobación humana pendiente' not in approved._replace_finality_text(escaped)
    evidence = 'Evidencia técnica: Decisión: Pendiente; identidad del revisor: Pendiente'
    assert approved._replace_finality_text(evidence) == evidence


def test_spanish_pdf_wrapped_delivery_sentence_is_certificate_controlled():
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1)
    document.drawString(50, 750, 'La aprobación humana autorizada sigue pendiente y la entrega al cliente permanece')
    document.drawString(50, 735, 'bloqueada.')
    document.save()
    source = buffer.getvalue()
    certificate = approved._certificate_pdf(reviewer='SYNTHETIC SOFTWARE-TEST',
        reviewer_role='Security reviewer', decision_reason='SYNTHETIC SOFTWARE-TEST',
        decided_at='2026-09-09T00:00:00Z', source_pdf_sha256=hashlib.sha256(source).hexdigest(),
        run_id='synthetic_generator_test', repository='synthetic/fixture', commit_sha='a'*40,
        spanish=True)
    final = approved._rewrite_pdf(source, certificate_pdf=certificate, spanish=True)
    text = PdfReader(io.BytesIO(final)).pages[0].extract_text()
    assert 'bloqueada' not in text
    assert 'se controla\npor separado.' in text
