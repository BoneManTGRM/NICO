"""Prove fail-closed applicability boundaries on immutable source."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

BASELINE = 'd3fbd5cbc318d188b8c2d230942569ad41a1fb9c'
FUNCTIONS = {'test_utf16_entity_remains_required', 'test_unknown_qt_element_remains_required',
             'test_case_distinct_path_cannot_be_suppressed', 'test_jsconfig_cannot_justify_absence',
             'test_supported_typescript_suffixes_cannot_justify_absence',
             'test_git_path_identity_precedes_text_cleanup', 'test_formatted_qt_path_is_unproven',
             'test_negative_word_in_git_path_cannot_justify_absence'}
NAMES = (FUNCTIONS - {'test_supported_typescript_suffixes_cannot_justify_absence',
                      'test_git_path_identity_precedes_text_cleanup'}) | {
    'test_supported_typescript_suffixes_cannot_justify_absence[mts]',
    'test_supported_typescript_suffixes_cannot_justify_absence[cts]',
    'test_git_path_identity_precedes_text_cleanup[leading-space]',
    'test_git_path_identity_precedes_text_cleanup[leading-punctuation]',
    'test_git_path_identity_precedes_text_cleanup[internal-whitespace]',
}
source = Path('qt-baseline')
observed = subprocess.run(['git', '-C', str(source), 'rev-parse', 'HEAD'],
                          check=True, capture_output=True, text=True, timeout=30).stdout.strip()
if observed != BASELINE:
    raise RuntimeError('qt_regression_baseline_source_mismatch')
# Prove pytest resolves the immutable baseline, not the editable corrected package.
probe = subprocess.run([
    sys.executable, '-c',
    "from pathlib import Path; import json; "
    "from nico import node_scanner_applicability_v1 as m; "
    "assert Path(m.__file__).resolve() == "
    "(Path.cwd() / 'nico/node_scanner_applicability_v1.py').resolve(); "
    "print(json.dumps({'node_inventory_module': str(Path(m.__file__).resolve())}))",
], cwd=source, check=True, capture_output=True, text=True, timeout=30)
for path in ('nico/node_scanner_applicability_v1.py', 'nico/scanner_applicability_v1.py'):
    original = subprocess.run(['git', '-C', str(source), 'show', 'HEAD:' + path],
                              check=True, capture_output=True, timeout=30).stdout
    if (source / path).read_bytes() != original:
        raise RuntimeError('qt_regression_baseline_file_modified')
tests = Path('tests/test_qt_translation_fail_closed.py').read_bytes()
(source / 'tests/test_qt_translation_fail_closed.py').write_bytes(tests)
results = Path('audit-results/qt-applicability')
results.mkdir(parents=True, exist_ok=True)
junit = results.resolve() / 'red.xml'
completed = subprocess.run([
    sys.executable, '-m', 'pytest', '-q', 'tests/test_qt_translation_fail_closed.py',
    '-k', ' or '.join(sorted(FUNCTIONS)), '--junitxml=' + str(junit),
], cwd=source, capture_output=True, text=True, timeout=90)
(results / 'red.log').write_text(completed.stdout + completed.stderr, encoding='utf-8')
cases = list(ET.parse(junit).getroot().iter('testcase'))
failed = {case.get('name') for case in cases if case.find('failure') is not None}
errors = [case for case in cases if case.find('error') is not None]
if completed.returncode != 1 or len(cases) != len(NAMES) or failed != NAMES or errors:
    raise RuntimeError('qt_minimal_regressions_did_not_fail_at_expected_boundaries')
expected_boundaries = {
    'test_utf16_entity_remains_required': "qt_translation_files",
    'test_unknown_qt_element_remains_required': "qt_translation_files",
    'test_case_distinct_path_cannot_be_suppressed': "applicability_state",
    'test_jsconfig_cannot_justify_absence': "applicability_state",
    'test_supported_typescript_suffixes_cannot_justify_absence[mts]': "applicability_state",
    'test_supported_typescript_suffixes_cannot_justify_absence[cts]': "applicability_state",
    'test_git_path_identity_precedes_text_cleanup[leading-space]': "applicability_state",
    'test_git_path_identity_precedes_text_cleanup[leading-punctuation]': "applicability_state",
    'test_git_path_identity_precedes_text_cleanup[internal-whitespace]': "applicability_state",
    'test_formatted_qt_path_is_unproven': "applicability_state",
    'test_negative_word_in_git_path_cannot_justify_absence': "applicability_state",
}
for case in cases:
    detail = case.find('failure').text or ''
    if expected_boundaries[case.get('name')] not in detail:
        raise RuntimeError('qt_minimal_regression_failed_at_unexpected_assertion')
proof = {'baseline_source_sha': BASELINE,
         'test_module_sha256': hashlib.sha256(tests).hexdigest(),
         'expected_failing_assertions': sorted(NAMES), 'observed_failures': sorted(failed),
         'baseline_import': json.loads(probe.stdout),
         'corrected_source_sha': subprocess.run(['git', 'rev-parse', 'HEAD'], check=True,
             capture_output=True, text=True, timeout=30).stdout.strip(),
         'tests': len(cases), 'errors': len(errors), 'pytest_exit': completed.returncode}
(results / 'red-proof.json').write_text(json.dumps(proof, indent=2, sort_keys=True) + '\n')
print(json.dumps(proof, sort_keys=True))
