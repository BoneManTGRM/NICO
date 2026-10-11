"""Native JUnit declarations reject before expansion, for every supported encoding."""
import base64
import codecs

import pytest

from nico.assessment_cpp_full_project import _junit, validate_native
from nico.assessment_cpp_runtime_execution import _completed_sanitizer_test_failure
from nico.cppcheck_native_output import parse_native
from tests.test_assessment_cpp_full_project import native, plan


def xml_bytes(body, encoding):
    if encoding == 'utf-8':
        return body.encode('utf-8')
    if encoding == 'utf-16-le':
        return codecs.BOM_UTF16_LE + body.encode('utf-16-le')
    return codecs.BOM_UTF16_BE + body.encode('utf-16-be')


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16-le', 'utf-16-be'])
@pytest.mark.parametrize('declaration', [
    '<!DOCTYPE testsuite>',
    '<!DOCTYPE testsuite [<!ENTITY owned "owned">]>',
])
def test_bound_native_junit_rejects_declarations_before_accepting_test_outcome(encoding, declaration):
    contract = plan()
    evidence = native(contract)
    row = next(row for row in evidence['steps'] if row['id'] == 'baseline-unit')
    raw = xml_bytes(declaration + '<testsuite tests="1"><testcase name="unit" status="run"/></testsuite>', encoding)
    row['artifacts']['junit'] = base64.b64encode(raw).decode('ascii')
    result = validate_native(evidence, contract)
    stage = next(row for row in result['build']['stages'] if row['id'] == 'baseline-unit')
    assert stage['status'] == 'partial'
    assert stage['executed_tests'] is None and stage['passed_tests'] is None


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16-le', 'utf-16-be'])
def test_completed_sanitizer_failure_rejects_declared_entity_message(encoding):
    raw = xml_bytes('<!DOCTYPE testsuite [<!ENTITY outcome "Failed">]>'
                    '<testsuite tests="1"><testcase name="owned" status="fail">'
                    '<failure message="&outcome;"/></testcase></testsuite>', encoding)
    operation = {'exit_code': 8, 'timed_out': False, 'output_truncated': False}
    summary = {'required': ['owned'], 'executed': ['owned'], 'passed': [], 'skipped': []}
    assert _completed_sanitizer_test_failure(operation, summary, raw) is False


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16-le', 'utf-16-be'])
def test_plain_junit_preserves_supported_encoding_unicode_and_real_failure(encoding):
    raw = xml_bytes('<testsuite tests="2"><testcase name="clean" status="run">'
                    '<system-out>Niño café</system-out></testcase>'
                    '<testcase name="owned" status="fail"><failure message="Failed"/>'
                    '</testcase></testsuite>', encoding)
    assert _junit(raw, ['clean', 'owned']) == (['clean', 'owned'], ['clean'], [])
    summary = {'required': ['clean', 'owned'], 'executed': ['clean', 'owned'],
               'passed': ['clean'], 'skipped': []}
    assert _completed_sanitizer_test_failure(
        {'exit_code': 8, 'timed_out': False, 'output_truncated': False}, summary, raw
    ) is True


@pytest.mark.parametrize('encoding', ['utf-16-le', 'utf-16-be'])
def test_cppcheck_rejects_declarations_hidden_in_nul_bearing_decoded_output(encoding):
    raw = ('<!DOCTYPE results [<!ENTITY diagnostic "owned diagnostic">]>'
           '<results version="2"><cppcheck version="2.17.1"/><errors>'
           '<error id="owned" severity="warning" msg="&diagnostic;">'
           '<location file="owned.cpp" line="1"/></error></errors></results>')
    decoded = raw.encode(encoding).decode('utf-8')
    with pytest.raises(ValueError, match='cppcheck_xml_external_content_rejected'):
        parse_native(decoded, 'Checking owned.cpp ...\n', ['owned.cpp'], version='2.17.1')
