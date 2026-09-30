from copy import deepcopy
import hashlib

import pytest

from nico.node_scanner_applicability_v1 import inspect_node_inputs, justified_inapplicability, inventory_digest
from nico.scanner_applicability_v1 import normalize_scanner_applicability_canonical
from tests.test_node_scanner_applicability_inventory import scan, canonical
from nico.complete_assessment_gate_v1 import complete_assessment_evidence
from tests.test_scanner_completion_gate import SHA, RUN

QT = '<?xml version="1.0"?><!DOCTYPE TS><TS version="2.1" language="en"><context><name>Main</name><message><source>Bitcoin</source><translation>Bitcoin</translation></message></context></TS>'


def test_qt_translation_retains_content_identity_and_is_not_typescript(tmp_path, monkeypatch):
    path = 'src/qt/locale/bitcoin_en.ts'
    artifact = scan(tmp_path, monkeypatch, {path: QT})
    tool = artifact['tools']['typescript']
    inv = tool['applicability_evidence']
    assert inv['typescript_input_paths'] == []
    assert inv['qt_translation_files'] == [{'path': path, 'format': 'qt-ts-xml-v1',
        'sha256': hashlib.sha256(QT.encode()).hexdigest(), 'size_bytes': len(QT.encode())}]
    assert tool['status'] == 'not_applicable' and tool['completed'] is False
    value = canonical(artifact)
    value['repository_evidence'] = {'file_evidence': {'sampled_paths': [path]}}
    for _ in range(2):
        value = normalize_scanner_applicability_canonical(value)
        record = next(r for r in value['requested_scanner_records'] if r['scanner_name'] == 'typescript')
        assert record['applicability_state'] == 'not_applicable'
        assert record['completed'] is False
    assert complete_assessment_evidence(value, expected_commit=SHA, expected_run=RUN)['passed'] is True


@pytest.mark.parametrize('extra', [{'src/main.ts': 'export const n: number = 1;'}, {'tsconfig.json': '{}'},
    {'package.json': '{"scripts":{"check":"tsc --noEmit"}}'}])
def test_real_typescript_inputs_remain_required_beside_qt(tmp_path, extra):
    for name, text in {'translations.ts': QT, **extra}.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    inv = inspect_node_inputs(tmp_path, SHA)
    assert not justified_inapplicability(inv, 'typescript', SHA)


@pytest.mark.parametrize('content', ['export const x = 1;', '<TS version="2.1">',
    '<other/>', '<!DOCTYPE TS [<!ENTITY word "Bitcoin">]><TS version="2.1"><context><name>N</name><message><source>&word;</source></message></context></TS>'])
def test_unrecognized_or_incomplete_xml_cannot_exclude_ts(tmp_path, content):
    (tmp_path / 'input.ts').write_text(content)
    inv = inspect_node_inputs(tmp_path, SHA)
    assert inv['typescript_input_paths'] == ['input.ts']
    assert inv['qt_translation_files'] == []


def test_unknown_source_conflict_and_tampered_translation_stay_unproven(tmp_path, monkeypatch):
    artifact = scan(tmp_path, monkeypatch, {'translations.ts': QT})
    value = canonical(artifact)
    value['repository_evidence'] = {'file_evidence': {'sampled_paths': ['src/unknown.ts']}}
    record = normalize_scanner_applicability_canonical(value)['requested_scanner_records']
    assert next(r for r in record if r['scanner_name'] == 'typescript')['applicability_state'] == 'applicability_unproven'
    corrupt = deepcopy(value)
    ts = next(r for r in corrupt['requested_scanner_records'] if r['scanner_name'] == 'typescript')
    inv = ts['applicability_evidence']
    inv['qt_translation_files'][0]['sha256'] = 'invalid'
    inv['inventory_sha256'] = inventory_digest(inv)
    assert not justified_inapplicability(inv, 'typescript', SHA)
