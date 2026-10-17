"""PDF operand/state regressions for the operator renderer's extraction."""
import io
import json

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, BooleanObject, ByteStringObject, ContentStream, NameObject, NumberObject
from reportlab.pdfgen import canvas

from nico import comprehensive_operator_presentation_v1 as presentation


def source_pdf(spanish=False, literal=False, operator=b'Tj', references=True):
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1, pagesize=(612, 792))
    lines = (["Postura ejecutiva", "REVISIÓN HUMANA", "Pendiente", "ENTREGA AL CLIENTE", "Bloqueada",
              "Verdad de revisión humana y aprobación", "Aprobación humana final", "PENDIENTE",
              "Autorización de entrega al cliente", "BLOQUEADA",
              "Aprobación humana: Pendiente de una acción explícita del revisor."] if spanish else
             ["Executive posture", "HUMAN REVIEW", "Pending", "CLIENT DELIVERY", "Blocked",
              "Human Review and Approval Truth", "Final human approval", "PENDING",
              "Client-delivery authorization", "BLOCKED",
              "Human approval: Pending explicit reviewer action."])
    lines += ["BLOCKED - AUTHORIZED HUMAN APPROVAL", "Unrelated pending evidence", "REQUIRED",
              "REQUIRED", "Score 93/100", "QC 0/9"]
    for index, line in enumerate(lines):
        document.drawString(30, 750-index*20, line)
    document.showPage()
    if references:
        for _ in range(2):
            document.drawString(30, 750, "Registro de aprobación del operador" if spanish else "Operator Report Approval Record")
            document.showPage()
    document.save()
    writer = PdfWriter(clone_from=io.BytesIO(buffer.getvalue()))
    page = writer.pages[0]
    page[NameObject('/NICOSuppliedEvidence')] = BooleanObject(literal)
    stream = ContentStream(page.get_contents(), writer)
    rewritten = []
    for operands, current in stream.operations:
        if current == b'Tj':
            text = operands[0]
            if operator == b'TJ':
                operands = [ArrayObject([NumberObject(0), text, NumberObject(-20)])]
            elif operator == b'"':
                operands = [NumberObject(0), NumberObject(0), text]
            current = operator
        rewritten.append((operands, current))
    stream.operations = rewritten
    page.replace_contents(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.parametrize('operator', [b'Tj', b'TJ', b"'", b'"'])
@pytest.mark.parametrize('spanish', [False, True])
@pytest.mark.parametrize('authorized', [False, True])
@pytest.mark.parametrize('literal', [False, True])
def test_operand_state_literal_exclusion_and_last_reference(operator, spanish, authorized, literal):
    source = source_pdf(spanish, literal, operator)
    options = dict(client_delivery_authorized=authorized, repair_current_truth=True,
                   resolve_approval_references=True)
    rendered, changes = presentation._render_source.__wrapped__(source, **options)
    assert presentation._render_source.__wrapped__(source, **options) == (rendered, changes)
    text = PdfReader(io.BytesIO(rendered)).pages[0].extract_text()
    assert 'Score 93/100' in text and 'QC 0/9' in text
    assert 'Unrelated pending evidence' in text
    if literal:
        assert changes == ()
        assert text == PdfReader(io.BytesIO(source)).pages[0].extract_text()
    else:
        assert ('pág. 3 del informe' if spanish else 'report p. 3') in text
        assert [old for _, old, _ in changes].count('REQUIRED') == 1
        assert [new for _, old, new in changes if old == 'REQUIRED'] == [
            'AUTHORIZATION RECORDED' if authorized else 'SEPARATE AUTHORIZATION']
        assert all(page == 1 for page, _, _ in changes)
        assert [new for _, old, new in changes if old == ('BLOQUEADA' if spanish else 'BLOCKED')] == (
            ['AUTORIZADA' if spanish else 'AUTHORIZED'] if authorized else [])


def test_missing_reference_remains_an_error():
    with pytest.raises(ValueError, match='^operator_approval_reference_target_missing$'):
        presentation._render_source.__wrapped__(source_pdf(references=False), resolve_approval_references=True)


def test_receipt_page_size_mismatch_remains_an_error():
    out = io.BytesIO()
    document = canvas.Canvas(out, invariant=1, pagesize=(400, 400))
    document.drawString(20, 350, 'Human Review and Exact-Artifact Approval; Reviewer identity')
    document.save()
    receipt = {'source_identity': {'report_language': 'en', 'run_id': 'fixture'},
               'source_review_artifact_identity': {'revision': 1}}
    with pytest.raises(ValueError, match='^operator_approval_record_pagination_mismatch$'):
        presentation._render_source.__wrapped__(out.getvalue(), approval_receipt_json=json.dumps(receipt))


def test_byte_string_operands_retain_latin1_type_and_order(monkeypatch):
    original_stream = presentation.ContentStream
    captured = []

    def byte_stream(*args, **kwargs):
        stream = original_stream(*args, **kwargs)
        for operands, operator in stream.operations:
            if operator == b'Tj':
                operands[0] = ByteStringObject(str(operands[0]).encode('latin-1'))
        captured.append(stream)
        return stream

    monkeypatch.setattr(presentation, 'ContentStream', byte_stream)
    _, changes = presentation._render_source.__wrapped__(source_pdf(), repair_current_truth=True)
    assert changes
    assert all(isinstance(operands[0], ByteStringObject)
               for stream in captured for operands, op in stream.operations if op == b'Tj')
    assert next(new for _, old, new in changes if old == 'HUMAN REVIEW') == 'OPERATOR APPROVAL'
