"""Refresh only the owned phase overlay after delivery authority validation."""
import io
from copy import deepcopy

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ContentStream

from nico.comprehensive_four_phase_model_v1 import _spanish
from nico.comprehensive_four_phase_pdf_v1 import _overlay, four_phase_target_page_index


def _text_operations(operations):
    # Unknown text operators must not be silently removed with the owned box.
    if any(op in (b'TJ', b"'", b'"') for _args, op in operations):
        return None
    # Wrapping can differ with embedded font metrics; preserve every word.
    return ' '.join(' '.join(str(value) for args, op in operations
                            if op == b'Tj' for value in args).split())


def _groups(operations):
    depth = 0
    start = 0
    for index, (_args, op) in enumerate(operations):
        if op == b'q':
            if depth == 0:
                start = index
            depth += 1
        elif op == b'Q':
            depth -= 1
            if depth == 0:
                yield start, index + 1
    if depth:
        raise ValueError('unbalanced_phase_pdf_graphics')


def refresh_authorized_phase_pdf(pdf, canonical):
    """Replace an exact known overlay, preserving all other page content.

    Legacy approval rendering stays frozen for historical receipt validation.
    A text/structure mismatch fails closed instead of rewriting source quotations.
    """
    if canonical.get('report_truth_schema') != 'nico.report_truth.v2':
        return pdf
    source = deepcopy(canonical)
    program = source.get('four_phase_program', {})
    phases = program.get('phases', [])
    if len(phases) != 4 or phases[3].get('id') != 'approval_and_client_delivery':
        raise ValueError('authorized_phase_program_missing')
    if phases[3].get('status') != 'authorized':
        raise ValueError('authorized_phase_canonical_state_mismatch')
    spanish = _spanish(source)
    reader = PdfReader(io.BytesIO(pdf))
    target = four_phase_target_page_index(reader, spanish=spanish)
    writer = PdfWriter(clone_from=reader)
    page = writer.pages[target]
    size = float(page.mediabox.width), float(page.mediabox.height)
    current_overlay = PdfReader(io.BytesIO(_overlay(source, spanish, size)))
    current_text = _text_operations(ContentStream(current_overlay.pages[0].get_contents(), current_overlay).operations)
    known_text = [current_text]
    for status in ('blocked_pending_authorized_human_approval', 'approved_pending_delivery_authorization'):
        phases[3]['status'] = status
        old = PdfReader(io.BytesIO(_overlay(source, spanish, size)))
        known_text.append(_text_operations(ContentStream(old.pages[0].get_contents(), old).operations))
    stream = ContentStream(page.get_contents(), writer)
    candidates = [(start, end) for start, end in _groups(stream.operations)
                  if _text_operations(stream.operations[start:end]) in known_text]
    if len(candidates) != 1:
        raise ValueError('authorized_phase_overlay_not_uniquely_identified')
    start, end = candidates[0]
    if _text_operations(stream.operations[start:end]) == current_text:
        return pdf
    # Remove the complete isolated overlay: no hidden stale text beneath new ink.
    stream.operations = stream.operations[:start] + stream.operations[end:]
    page.replace_contents(stream)
    page.merge_page(current_overlay.pages[0])
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
