"""Fail-closed Qt recognition; case-sensitive Git identity precedes suffix folding."""
import hashlib

import pytest

from nico.node_scanner_applicability_v1 import (
    MAX_QT_TRANSLATION_BYTES, _qt_translation, inspect_node_inputs,
    justified_inapplicability,
)
from nico.scanner_applicability_v1 import normalize_scanner_applicability_canonical

SHA = 'a' * 40
QT = ('<TS version="2.1"><context><name>N</name><message>'
      '<source>Bitcoin</source><translation>Bitcoin</translation>'
      '</message></context></TS>')
ENTITY = ('<!DOCTYPE TS [<!ENTITY word "Bitcoin">]>'
          '<TS version="2.1"><context><name>N</name><message>'
          '<source>&word;</source><translation>&word;</translation>'
          '</message></context></TS>')


def assert_required(repo, path, raw):
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    inventory = inspect_node_inputs(repo, SHA)
    assert inventory['qt_translation_files'] == []
    assert inventory['typescript_input_paths'] == [path]
    assert not justified_inapplicability(inventory, 'typescript', SHA)


def canonical(inventory, paths):
    return {'commit_sha': SHA, 'requested_scanner_records': [{
        'scanner_name': 'typescript', 'commit_sha': SHA,
        'status': 'not_applicable', 'completed': False,
        'execution_observed': False, 'execution_observed_for_this_report': False,
        'applicability_evidence': inventory,
    }], 'repository_evidence': {'file_evidence': {'sampled_paths': paths}}}


def test_utf16_entity_remains_required(tmp_path):
    assert_required(tmp_path, 'input.ts', ENTITY.encode('utf-16'))


def test_unknown_qt_element_remains_required(tmp_path):
    assert_required(tmp_path, 'input.ts',
                    QT.replace('<context>', '<unsupported/><context>').encode())


def test_case_distinct_path_cannot_be_suppressed(tmp_path):
    folder = tmp_path / 'src'
    folder.mkdir()
    (folder / 'foo.ts').write_text(QT)
    inventory = inspect_node_inputs(tmp_path, SHA)
    assert inventory['typescript_input_paths'] == []
    # Positive retained source contradicts a complete absence observation.
    # Linux/Git src/Foo.ts is not the verified src/foo.ts translation.
    (folder / 'Foo.ts').write_text('export const value: number = 1;')
    value = canonical(inventory, ['src/foo.ts', 'src/Foo.ts'])
    record = normalize_scanner_applicability_canonical(value)['requested_scanner_records'][0]
    assert record['applicability_state'] == 'applicability_unproven'
    assert record['evidence_required'] is True


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be'])
def test_entities_rejected_before_xml_parser(tmp_path, monkeypatch, encoding):
    raw = ENTITY.encode(encoding)
    if encoding == 'utf-16-le':
        raw = b'\xff\xfe' + raw
    elif encoding == 'utf-16-be':
        raw = b'\xfe\xff' + raw

    def forbidden_parse(*_args, **_kwargs):
        pytest.fail('Entity-bearing input reached XML parsing')

    monkeypatch.setattr('nico.node_scanner_applicability_v1.ET.fromstring', forbidden_parse)
    assert_required(tmp_path, 'input.ts', raw)


@pytest.mark.parametrize('declaration', ['<!ENTITY word "Bitcoin">',
                                        '<!eNtItY word "Bitcoin">'])
def test_entity_guard_is_case_insensitive_before_parse(tmp_path, monkeypatch, declaration):
    raw = ENTITY.replace('<!ENTITY word "Bitcoin">', declaration).encode('utf-16')
    monkeypatch.setattr('nico.node_scanner_applicability_v1.ET.fromstring',
                        lambda *_args, **_kwargs: pytest.fail('Entity reached parser'))
    assert_required(tmp_path, 'input.ts', raw)


@pytest.mark.parametrize('closing', ['</TS>', '</context>', '</message>',
                                    '</source>', '</translation>'])
def test_unknown_nodes_at_every_supported_boundary_remain_required(tmp_path, closing):
    assert_required(tmp_path, 'input.ts',
                    QT.replace(closing, '<unsupported/>' + closing).encode())


@pytest.mark.parametrize('version', ['2.0', '2.1'])
@pytest.mark.parametrize('encoding', ['utf-8', 'utf-8-sig', 'utf-16', 'utf-16-be'])
def test_supported_entity_free_documents_preserve_exact_bytes(tmp_path, version, encoding):
    text = ('<?xml version="1.0"?><!DOCTYPE TS>' +
            QT.replace('2.1', version).replace('Bitcoin', 'México'))
    raw = text.encode(encoding)
    if encoding == 'utf-16-be':
        raw = b'\xfe\xff' + raw
    (tmp_path / 'input.ts').write_bytes(raw)
    inventory = inspect_node_inputs(tmp_path, SHA)
    assert inventory['typescript_input_paths'] == []
    assert inventory['qt_translation_files'] == [{
        'path': 'input.ts', 'format': 'qt-ts-xml-v1',
        'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': len(raw),
    }]
    assert justified_inapplicability(inventory, 'typescript', SHA)
    record = normalize_scanner_applicability_canonical(
        canonical(inventory, ['input.ts']))['requested_scanner_records'][0]
    assert record['completed'] is False
    assert record['verified'] is False


@pytest.mark.parametrize('raw', [
    QT.encode('utf-16-le'), QT.encode('utf-16-be'), QT.encode('utf-32'),
    ('<?xml version="1.0" encoding="iso-8859-1"?>' + QT).encode('latin-1'),
    ('<!DOCTYPE TS SYSTEM "https://example.invalid/ts.dtd">' + QT).encode(),
    ('<!DOCTYPE TS [<!ELEMENT TS ANY>]>' + QT).encode(),
    QT.replace('version="2.1"', 'version="3.0"').encode(),
    QT.replace('<source>', '<source unsafe="true">').encode(),
    QT.replace('</message>', '<source>Duplicate</source></message>').encode(),
    QT.replace('<name>N</name>', '').encode(),
    QT.replace('<translation>Bitcoin</translation><', '<translation>Bitcoin</translation>noise<').encode(),
    QT.replace('<TS ', '<TS xmlns="urn:unknown" ').encode(),
])
def test_ambiguous_unsupported_or_contradictory_xml_remains_required(tmp_path, raw):
    assert_required(tmp_path, 'input.ts', raw)


def test_case_distinct_real_typescript_remains_required(tmp_path):
    folder = tmp_path / 'src'
    folder.mkdir()
    (folder / 'foo.ts').write_text(QT)
    (folder / 'Foo.ts').write_text('export const value: number = 1;')
    inventory = inspect_node_inputs(tmp_path, SHA)
    assert inventory['typescript_input_paths'] == ['src/Foo.ts']
    assert [item['path'] for item in inventory['qt_translation_files']] == ['src/foo.ts']
    assert not justified_inapplicability(inventory, 'typescript', SHA)
    record = normalize_scanner_applicability_canonical(
        canonical(inventory, ['src/foo.ts', 'src/Foo.ts']))['requested_scanner_records'][0]
    assert record['applicability_state'] == 'applicable'
    assert record['evidence_required'] is True


def test_exact_path_separator_normalization_preserves_nonexecution(tmp_path):
    folder = tmp_path / 'src'
    folder.mkdir()
    (folder / 'Foo.ts').write_text(QT)
    inventory = inspect_node_inputs(tmp_path, SHA)
    record = normalize_scanner_applicability_canonical(
        canonical(inventory, ['src\\Foo.ts']))['requested_scanner_records'][0]
    assert record['applicability_state'] == 'not_applicable'
    assert record['completed'] is False and record['evidence_required'] is False


def test_size_bound_rejects_without_xml_parsing(tmp_path, monkeypatch):
    monkeypatch.setattr('nico.node_scanner_applicability_v1.ET.fromstring',
                        lambda *_args, **_kwargs: pytest.fail('Oversized input reached parser'))
    assert_required(tmp_path, 'input.ts', b'x' * (MAX_QT_TRANSLATION_BYTES + 1))


def test_optional_translation_and_plural_forms_are_supported(tmp_path):
    text = ('<TS version="2.0"><context><name>N</name>'
            '<message><source>Untranslated</source></message>'
            '<message numerus="yes"><source>%n values</source>'
            '<extracomment>Keep the count</extracomment>'
            '<translation type="unfinished"><numerusform>%n value</numerusform>'
            '<numerusform>%n values</numerusform></translation></message>'
            '</context></TS>')
    (tmp_path / 'input.ts').write_text(text)
    inventory = inspect_node_inputs(tmp_path, SHA)
    assert justified_inapplicability(inventory, 'typescript', SHA)

@pytest.mark.parametrize('translation', [
    '<translation variants="yes">text</translation>',
    '<translation variants="yes"><byte value="65"/></translation>',
    '<translation><lengthvariant>text</lengthvariant></translation>',
    '<translation><numerusform variants="yes">text</numerusform></translation>',
])
def test_unsupported_variant_structure_remains_required(tmp_path, translation):
    text = QT.replace('<translation>Bitcoin</translation>', translation)
    if 'numerusform' in translation:
        text = text.replace('<message>', '<message numerus="yes">')
    assert_required(tmp_path, 'input.ts', text.encode())


def test_supported_length_variants_and_source_bytes(tmp_path):
    text = QT.replace('<source>Bitcoin</source>',
                      '<source>Bit<byte value="120"/>coin</source>').replace(
        '<translation>Bitcoin</translation>',
        '<translation variants="yes"><lengthvariant>Bitcoin</lengthvariant>'
        '<lengthvariant>BTC</lengthvariant></translation>')
    (tmp_path / 'input.ts').write_text(text)
    assert justified_inapplicability(inspect_node_inputs(tmp_path, SHA),
                                    'typescript', SHA)

@pytest.mark.parametrize('text', [
    '<?unsupported x?>' + QT,
    QT + '<?unsupported x?>',
    QT.replace('<context>', '<?unsupported x?><context>'),
    QT.replace('<source>', '<?unsupported x?><source>'),
])
@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16'])
def test_processing_instructions_remain_unsupported(tmp_path, text, encoding):
    assert_required(tmp_path, 'input.ts', text.encode(encoding))


def test_comments_with_pi_like_text_are_supported(tmp_path):
    text = QT.replace('<context>', '<!-- <?example text?> --><context>')
    (tmp_path / 'input.ts').write_text(text)
    assert justified_inapplicability(inspect_node_inputs(tmp_path, SHA),
                                    'typescript', SHA)
