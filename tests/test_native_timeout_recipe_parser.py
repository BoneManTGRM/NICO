"""Text-only controls: no diagnostic module import or native execution."""
import ast
from pathlib import Path
import re
import pytest

@pytest.fixture
def parser():
    tree = ast.parse(Path('scripts/native_timeout_diagnostic.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'provision_script')
    scope = {'re': re}
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<recipe parser>', 'exec'), scope)
    return scope['provision_script']

def workflow(metadata='', body='          echo owned\n'):
    return ('jobs:\n  project-baseline-qualification:\n    steps:\n'
            '      - name: Owned recipe\n' + metadata + '        run: |\n' + body)

@pytest.mark.parametrize('metadata', ['', '        id: collection_image\n'])
def test_step_id_preserves_recipe(parser, metadata):
    assert parser(workflow(metadata), 'Owned recipe') == 'echo owned\n'

@pytest.mark.parametrize('metadata', [
    '        if: false\n', '        env: {}\n', '        shell: bash\n',
    '        id: ${{ x }}\n', '        id: "quoted"\n',
    '        id: first\n        id: second\n', '        id: valid\n        if: false\n'])
def test_unsupported_metadata_rejected(parser, metadata):
    with pytest.raises(ValueError, match='diagnostic_recipe_step_invalid'):
        parser(workflow(metadata), 'Owned recipe')

def test_duplicate_name_rejected(parser):
    text = workflow() + workflow('        id: second\n').split('    steps:\n')[1]
    with pytest.raises(ValueError, match='diagnostic_recipe_step_invalid'):
        parser(text, 'Owned recipe')

@pytest.mark.parametrize('body', ['', '          echo ${{ x }}\n'])
def test_invalid_body_rejected(parser, body):
    with pytest.raises(ValueError, match='diagnostic_recipe_interpolation_unsupported'):
        parser(workflow(body=body), 'Owned recipe')

def test_next_step_excluded(parser):
    text = workflow('        id: collection_image\n') + '      - name: next\n        run: other\n'
    assert parser(text, 'Owned recipe') == 'echo owned\n'
