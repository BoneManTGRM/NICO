"""Offline composition against immutable pinned upstream source objects.

Set NICO_CPPCHECK_SOURCE to a local official Cppcheck checkout containing the
pinned commit. No fetching, native execution, containers, or baseline comparison.
"""
import hashlib
import os
from pathlib import Path
import subprocess

import pytest

from scripts import repair_cppcheck_placement_ast as ast
from scripts import repair_cppcheck_header_grammar as grammar
from scripts import patch_cppcheck_header_evidence as observer


def test_grammar_requires_exact_combined_ast_output():
    assert grammar.PATCHES['lib/tokenlist.cpp'][0] == '39f33db14a8d4cd359c1f1c8ae5a4eacb534acfa'


@pytest.fixture
def pinned_sources(tmp_path):
    checkout = os.environ.get('NICO_CPPCHECK_SOURCE')
    if not checkout:
        pytest.skip('set NICO_CPPCHECK_SOURCE for pinned-source composition evidence')
    root = tmp_path / 'upstream'
    originals = {}
    for name in sorted(set(grammar.PATCHES) | observer.SOURCES):
        raw = subprocess.run(
            ['git', '-C', checkout, 'show', f'{ast.UPSTREAM_COMMIT}:{name}'],
            check=True, capture_output=True, timeout=10).stdout
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        originals[name] = raw
    assert ast.git_blob(originals['lib/tokenlist.cpp']) == ast.UPSTREAM_BLOB
    return root, originals


def test_actual_pinned_patch_sequence_and_receipts(pinned_sources):
    root, originals = pinned_sources
    ast_receipt = ast.apply_repair(root / 'lib/tokenlist.cpp')
    ast_output = (root / 'lib/tokenlist.cpp').read_bytes()
    assert ast_receipt['source_after_git_blob'] == grammar.PATCHES['lib/tokenlist.cpp'][0]
    grammar_receipt = grammar.apply_repair(root)
    final_tokenlist = (root / 'lib/tokenlist.cpp').read_bytes()
    assert ast.METHOD_REPLACEMENT in final_tokenlist
    assert ast.REPLACEMENT in final_tokenlist
    # This later grammar repair must not touch shared function-head recognition.
    marker = b'const Token * TokenList::isFunctionHead('
    assert final_tokenlist[final_tokenlist.index(marker):] == originals['lib/tokenlist.cpp'][originals['lib/tokenlist.cpp'].index(marker):]
    for member in grammar_receipt['members']:
        name = member['source_path']
        before = ast_output if name == 'lib/tokenlist.cpp' else originals[name]
        assert member['source_before_sha256'] == hashlib.sha256(before).hexdigest()
        assert member['source_after_sha256'] == hashlib.sha256((root / name).read_bytes()).hexdigest()
    assert not set(grammar.PATCHES) & observer.SOURCES
    grammar_outputs = {name: (root / name).read_bytes() for name in grammar.PATCHES}
    observer_receipt = observer.apply_header_patch(root, Path('scripts/cppcheck-header-evidence'))
    assert observer_receipt['qualification_completed'] is False
    assert grammar_outputs == {name: (root / name).read_bytes() for name in grammar.PATCHES}


def test_placement_only_input_is_rejected_before_any_grammar_write(pinned_sources):
    root, originals = pinned_sources
    # Source-byte integrity control, not an old/current native binary comparison.
    raw = originals['lib/tokenlist.cpp']
    (root / 'lib/tokenlist.cpp').write_bytes(raw.replace(ast.ANCHOR, ast.REPLACEMENT, 1))
    before = {name: (root / name).read_bytes() for name in originals}
    with pytest.raises(ValueError, match='upstream_source_mismatch'):
        grammar.apply_repair(root)
    assert before == {name: (root / name).read_bytes() for name in originals}
