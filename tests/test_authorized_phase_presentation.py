"""Synthetic lifecycle regression; no live approval or assessment is created."""
import base64
import io
from copy import deepcopy

import pytest
from pypdf import PdfReader

from nico.comprehensive_four_phase_model_v1 import apply_four_phase_program
from nico.comprehensive_four_phase_pdf_v1 import apply_four_phase_pdf
from nico.comprehensive_operator_delivery_v1 import render_delivery_companion_presentation
from nico.comprehensive_operator_approval_v1 import _artifact_digests
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from tests.test_comprehensive_four_phase_report_v1 import _canonical, _pdf


def edition(language):
    source = apply_four_phase_program(_canonical(language=language))
    pdf = apply_four_phase_pdf(_pdf(), source)
    source['report_truth_schema'] = 'nico.report_truth.v2'
    source['four_phase_program']['phases'][3]['status'] = 'authorized'
    reports = {'json': source, 'markdown': 'Literal: APPROVAL REQUIRED',
               'html': '<p>Literal: APPROVAL REQUIRED</p>',
               'pdf_base64': base64.b64encode(pdf).decode()}
    digests = _artifact_digests(reports)
    return {'reports': reports, 'artifact_digests': digests,
            'report_artifact_digest': canonical_sha256(digests),
            'review': {'approval_certificate_sha256': 'a' * 64},
            'delivery_authorization': {'delivery_authorization_certificate_sha256': 'b' * 64},
            'accepted_edition_manifest_sha256': 'c' * 64}


@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_authorized_matrix_refresh_preserves_original_authority_and_is_idempotent(language):
    original = edition(language)
    frozen = deepcopy(original)
    before = PdfReader(io.BytesIO(base64.b64decode(original['reports']['pdf_base64'])))
    result = render_delivery_companion_presentation(original)
    after = PdfReader(io.BytesIO(base64.b64decode(result['reports']['pdf_base64'])))
    text = '\n'.join(p.extract_text() for p in after.pages)
    assert ('BLOQUEADA' if language == 'es-MX' else 'BLOCKED') not in text
    assert ('AUTORIZADA' if language == 'es-MX' else 'AUTHORIZED') in text
    assert original == frozen
    assert result['reports']['json'] == original['reports']['json']
    assert result['reports']['markdown'] == original['reports']['markdown']
    assert result['reports']['html'] == original['reports']['html']
    assert result['review'] == original['review']
    assert result['delivery_authorization'] == original['delivery_authorization']
    assert len(after.pages) == len(before.pages)
    assert after.pages[0].extract_text() == before.pages[0].extract_text()
    assert render_delivery_companion_presentation(result) == result
    assert result['artifact_digests'] == _artifact_digests(result['reports'])
    manifest = deepcopy(result)
    claimed = manifest.pop('accepted_edition_manifest_sha256')
    assert canonical_sha256(manifest) == claimed
    assert result['rendering_derivation']['new_human_approval'] is False
    assert result['rendering_derivation']['authoritative_delivery_manifest_sha256'] == original['accepted_edition_manifest_sha256']


def test_unknown_matrix_content_and_unestablished_authority_fail_closed():
    from nico.comprehensive_authorized_phase_pdf import refresh_authorized_phase_pdf
    from pypdf import PdfWriter
    from pypdf.generic import ContentStream, TextStringObject
    original = edition('en')
    pdf = base64.b64decode(original['reports']['pdf_base64'])
    canonical = deepcopy(original['reports']['json'])
    canonical['four_phase_program']['phases'][3]['status'] = 'not_established'
    with pytest.raises(ValueError, match='canonical_state_mismatch'):
        refresh_authorized_phase_pdf(pdf, canonical)
    writer = PdfWriter(clone_from=io.BytesIO(pdf))
    page = writer.pages[1]
    stream = ContentStream(page.get_contents(), writer)
    for args, op in stream.operations:
        if op == b'Tj' and args and str(args[0]) == 'LIMITED':
            args[0] = TextStringObject('Literal evidence: LIMITED')
    page.replace_contents(stream)
    output = io.BytesIO(); writer.write(output)
    with pytest.raises(ValueError, match='not_uniquely_identified'):
        refresh_authorized_phase_pdf(output.getvalue(), original['reports']['json'])


def test_legacy_source_is_not_reinterpreted():
    from nico.comprehensive_authorized_phase_pdf import refresh_authorized_phase_pdf
    assert refresh_authorized_phase_pdf(b'original historical bytes', {}) == b'original historical bytes'
