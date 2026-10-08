"""Pinned Cppcheck grammar repair for physical compiler-header inputs.

Only trusted analyzer sources change. Assessed and generated sources, compiler
defines, observer events and required checks are preserved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

try:
    from .repair_cppcheck_placement_ast import _read, git_blob, UPSTREAM_COMMIT
except ImportError:  # Standalone image-build invocation.
    from repair_cppcheck_placement_ast import _read, git_blob, UPSTREAM_COMMIT

REPAIR_ID = 'physical-header-grammar-v1'
PATCHES = {
    'lib/tokenize.cpp': (
        'f1fd9b0b1616e6ee3bfd2351f11ecede9353ed59',
        b'        while (Token::Match(ftok, "%name%|::|<|*|& !!(")) {\n',
        b'        while (Token::Match(ftok, "%name%|::|<|*|& !!(")) {\n'
        b'            // Prefix attributes also attach to overloaded operators.\n'
        b'            if (isCPP() && (Token::simpleMatch(ftok, "operator [ ] (") ||\n'
        b'                            Token::simpleMatch(ftok, "operator ( ) (") ||\n'
        b'                            Token::Match(ftok, "operator %op% (")))\n'
        b'                return ftok;\n',
    ),
    'lib/token.cpp': (
        'c28d664faabb8994b876e14da40fee71b7da4f01',
        b'                 (templateParameter ? templateParameters.find(closing->strAt(-1)) == templateParameters.end() : true))\n',
        b'                 // A qualified function-template call is not the same-named parameter.\n'
        b'                 (templateParameter ? (templateParameters.find(closing->strAt(-1)) == templateParameters.end() ||\n'
        b'                                       (Token::simpleMatch(closing->tokAt(-2), "::") &&\n'
        b'                                        closing->findClosingBracket() &&\n'
        b'                                        Token::simpleMatch(closing->findClosingBracket()->next(), "("))) : true))\n',
    ),
    # Exact output of the existing pinned placement-new repair.
    'lib/tokenlist.cpp': (
        'f6e28dfb9bb4358d93fa6ab5ac227346164880a3',
        b'            tok = findCppTypeInitPar(tok);\n'
        b'            state.op.push(tok);\n'
        b'            tok = tok->tokAt(2);\n',
        b'            Token *const par = findCppTypeInitPar(tok);\n'
        b'            Token *argument = par->next();\n'
        b'            AST_state argumentState(state.cpp);\n'
        b'            argumentState.depth = state.depth + 1;\n'
        b'            if (argumentState.depth > AST_MAX_DEPTH)\n'
        b'                throw InternalError(argument, "maximum AST depth exceeded", InternalError::AST);\n'
        b'            compileExpression(argument, argumentState);\n'
        b'            if (!argumentState.op.empty())\n'
        b'                par->astOperand1(argumentState.op.top());\n'
        b'            state.op.push(par);\n'
        b'            tok = par->link()->next();\n',
    ),
}
EXTRA_REPLACEMENTS = {'lib/tokenize.cpp': (
    (b'                     !(tok->tokType() == Token::Type::eBoolean && cpp && Token::simpleMatch(tok->tokAt(-1), "requires")))',
     b'                     !(tok->tokType() == Token::Type::eBoolean && cpp && Token::simpleMatch(tok->tokAt(-1), "requires")) &&\n'
     b'                     !(cpp && mSettings.standards.cpp >= Standards::CPP20 &&\n'
     b'                       Token::Match(tok->tokAt(-3), "%type% %name% : %num% {")))'),
    (b'Token::Match(tok1, "%name% : %num% [;=]")',
     b'Token::Match(tok1, "%name% : %num% [;={]")'),
)}


def patched_bytes(relative: str, raw: bytes) -> bytes:
    blob, anchor, replacement = PATCHES[relative]
    if not isinstance(raw, bytes) or len(raw) > 2 * 1024 * 1024 or git_blob(raw) != blob:
        raise ValueError('upstream_source_mismatch')
    if raw.count(anchor) != 1:
        raise ValueError('upstream_anchor_mismatch')
    for old, _ in EXTRA_REPLACEMENTS.get(relative, ()):
        if raw.count(old) != 1:
            raise ValueError('upstream_anchor_mismatch')
    patched = raw.replace(anchor, replacement, 1)
    for old, new in EXTRA_REPLACEMENTS.get(relative, ()):
        patched = patched.replace(old, new, 1)
    return patched


def apply_repair(root: Path) -> dict:
    root = Path(root).absolute()
    if root != root.resolve(strict=True):
        raise ValueError('upstream_source_path_invalid')
    inputs = []
    # Validate every file before changing any.
    for relative in PATCHES:
        source = root / relative
        if source.parent != source.parent.resolve(strict=True):
            raise ValueError('upstream_source_path_invalid')
        raw, mode = _read(source)
        inputs.append((relative, source, raw, mode, patched_bytes(relative, raw)))
    members = []
    for relative, source, raw, mode, patched in inputs:
        descriptor, name = tempfile.mkstemp(prefix='.nico-grammar-', dir=source.parent)
        try:
            with os.fdopen(descriptor, 'wb') as handle:
                handle.write(patched)
                handle.flush()
                os.fchmod(handle.fileno(), mode)
                os.fsync(handle.fileno())
            if _read(source)[0] != raw:
                raise ValueError('upstream_source_changed')
            os.replace(name, source)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        members.append({'source_path': relative, 'source_before_git_blob': git_blob(raw),
            'source_after_git_blob': git_blob(patched),
            'source_before_sha256': hashlib.sha256(raw).hexdigest(),
            'source_after_sha256': hashlib.sha256(patched).hexdigest()})
    return {'schema': 'nico.cppcheck-header-grammar-repair.v1', 'repair_id': REPAIR_ID,
        'upstream_commit': UPSTREAM_COMMIT, 'members': members,
        'repair_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'base_tool_version': '2.17.1', 'native_qualification_completed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    print(json.dumps(apply_repair(parser.parse_args().root), sort_keys=True))


if __name__ == '__main__':
    main()
