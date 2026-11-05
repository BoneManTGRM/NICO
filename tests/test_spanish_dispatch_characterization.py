"""Exact-output cases captured from main 35604fa7 before dispatch refactoring."""
import ast
import json
from pathlib import Path

import pytest

from nico import comprehensive_spanish_canonical_report_v87 as presentation


# Test the authored dispatcher, independently of bootstrap-installed wrappers.
_source = ast.parse(Path(presentation.__file__).read_text())
_function = next(node for node in _source.body
                 if isinstance(node, ast.FunctionDef)
                 and node.name == '_structured_presentation_es')
_namespace = dict(vars(presentation))
exec(compile(ast.Module(body=[_function], type_ignores=[]),
             presentation.__file__, 'exec'), _namespace)
_dispatch = _namespace['_structured_presentation_es']
_cases = json.loads((Path(__file__).parent / 'fixtures' /
                     'spanish_dispatch_characterization.json').read_text())


@pytest.mark.parametrize('source,expected', _cases.items())
def test_baseline_dispatch_contract(source, expected):
    if expected[0] == 'ValueError':
        with pytest.raises(ValueError) as error:
            _dispatch(source)
        assert str(error.value) == expected[1]
    else:
        assert _dispatch(source) == expected[1]


def test_embedded_rule_text_and_braces_remain_literal():
    source = 'OSV lookup unavailable: Workflow jobs for run {literal} were returned without a jobs list.'
    assert _dispatch(source) == (
        'La consulta a OSV no estaba disponible; detalle técnico original: '
        'Workflow jobs for run {literal} were returned without a jobs list.'
    )
    assert _dispatch('Classification counts: {"template": "{count}"}.') == (
        'Conteos por clasificación: {"template": "{count}"}.'
    )
