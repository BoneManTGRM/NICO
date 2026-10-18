from copy import deepcopy
import json

import pytest

from nico import ordinary_bundle_boundary_v2 as boundary
from nico.decision_grade_accepted_edition_v2 import build_accepted_report_edition
from tests.test_decision_grade_accepted_edition_v2 import BASE


def escaped(value):
    return ''.join('\\u%04x' % ord(char) for char in value)


DECLARATIONS = [
    '{"artifact_schema":"'+escaped('nico.ordinary-report-files.v2')+'"}',
    '{"'+escaped('artifact_schema')+'":"'+escaped('nico.ordinary-review-bundle.v2')+'"}',
    '{"'+escaped('report_bundle')+'":{}}',
    '{"'+escaped('report_bundle_schema')+'":"v2"}',
]


@pytest.mark.parametrize('raw',DECLARATIONS)
def test_unicode_escaped_declarations_cannot_downgrade(raw):
    assert boundary.has_report_bundle({'json':json.loads(raw)})
    assert boundary.has_report_bundle({'json':raw})
    with pytest.raises(ValueError,match=boundary.ERROR):
        boundary.require_legacy_single_pdf({'artifacts':{'json':raw}})


@pytest.mark.parametrize('raw',DECLARATIONS)
@pytest.mark.parametrize('encoding',['text','bytes','bytearray'])
def test_real_legacy_accepted_edition_rejects_escaped_declaration(raw,encoding):
    request=deepcopy(BASE)
    request['artifacts']['json']=raw if encoding=='text' else raw.encode() if encoding=='bytes' else bytearray(raw.encode())
    with pytest.raises(ValueError,match=boundary.ERROR):
        build_accepted_report_edition(**request)


@pytest.mark.parametrize('raw',['{broken','{"report_bundle":','[]','null','"canonical"',
                               '{"score":NaN}', '{"report_bundle":{},"report_bundle":null}'])
def test_malformed_or_ambiguous_report_json_fails_closed(raw):
    request=deepcopy(BASE);request['artifacts']['json']=raw
    with pytest.raises(ValueError):build_accepted_report_edition(**request)


def test_oversized_report_json_rejected_before_parsing(monkeypatch):
    monkeypatch.setattr(boundary,'MAX_REPORT_JSON_BYTES',32)
    raw=json.dumps({'padding':'x'*32})
    def forbidden(*args,**kwargs):pytest.fail('oversized JSON reached the parser')
    monkeypatch.setattr(boundary.json,'loads',forbidden)
    with pytest.raises(ValueError,match='size_limit'):
        boundary.require_legacy_single_pdf({'json':raw})
    request=deepcopy(BASE);request['artifacts']['json']=raw
    with pytest.raises(ValueError,match='size_limit'):build_accepted_report_edition(**request)


def test_utf8_byte_limit_not_character_count(monkeypatch):
    raw=json.dumps({'x':'é'*10},ensure_ascii=False)
    monkeypatch.setattr(boundary,'MAX_REPORT_JSON_BYTES',len(raw))
    with pytest.raises(ValueError,match='size_limit'):boundary.require_legacy_single_pdf({'json':raw})


def test_valid_v1_object_keeps_exact_bytes_and_receipt_digest():
    raw='{ "status" : "final", "label": "Espa\\u00f1ol" }\n'
    request=deepcopy(BASE);request['artifacts']['json']=raw
    result=build_accepted_report_edition(**request)
    import hashlib
    assert result['accepted_edition'] is True
    assert result['artifact_digests']['json']['sha256']==hashlib.sha256(raw.encode()).hexdigest()
    assert request['artifacts']['json']==raw


def test_evidence_quotations_are_not_recursively_interpreted():
    raw=json.dumps({'evidence':[json.loads(DECLARATIONS[0]),DECLARATIONS[2],'{malformed evidence']})
    assert not boundary.has_report_bundle({'json':raw})
    assert not boundary.has_report_bundle({'evidence':{'json':DECLARATIONS[0]}})


def test_invalid_unicode_json_is_rejected():
    with pytest.raises(ValueError,match='invalid_at_legacy_boundary'):
        boundary.require_legacy_single_pdf({'json':b'{"label":"\xff"}'})


def test_parser_recursion_failure_is_not_ignored(monkeypatch):
    def exhausted(*args,**kwargs):raise RecursionError('parser nesting limit')
    monkeypatch.setattr(boundary.json,'loads',exhausted)
    with pytest.raises(ValueError,match='invalid_at_legacy_boundary'):
        boundary.require_legacy_single_pdf({'json':'{}'})


def test_empty_required_artifact_keeps_existing_missing_artifact_result():
    request=deepcopy(BASE);request['artifacts']['json']=''
    result=build_accepted_report_edition(**request)
    assert result['accepted_edition'] is False
    assert 'missing_required_artifacts:json' in result['validation_errors']
