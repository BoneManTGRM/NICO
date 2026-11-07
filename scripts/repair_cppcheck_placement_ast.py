"""Source-pinned placement-new and constrained-constructor AST repairs.

Applied only to the trusted tool dependency while building its image. Assessed
source is never rewritten. Upstream license notices remain in the source/tool.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

UPSTREAM_COMMIT = 'ac9db3069b9f90e81e126a090b99ad456e122cf8'
UPSTREAM_BLOB = 'b9c3ab07f0436ada75da5f45c7f8c3f3e06a8608'
REPAIR_ID = 'placement-new-and-constructor-boundary-ast-v2'
SOURCE_LIMIT = 2 * 1024 * 1024
ANCHOR = b'            return !Token::Match(tok, "new ::| %type%");\n'
REPLACEMENT = (
    b'            // A placement argument list precedes the allocated type.\n'
    b'            // Keep its braced initializer on the new-expression path;\n'
    b'            // compileTerm would otherwise consume the outer scope node.\n'
    b'            if (Token::simpleMatch(tok, ")") && tok->link() &&\n'
    b'                Token::simpleMatch(tok->link()->previous(), "new ("))\n'
    b'                return false;\n' + ANCHOR
)
METHOD_ANCHOR = (
    b'    Token *const tok2 = const_cast<Token*>(TokenList::isFunctionHead(tok, ";{"));\n'
    b'    if (tok2 && tok->next() != tok2)\n'
    b'        return tok2;\n'
)
METHOD_REPLACEMENT = (
    b'    Token *const tok2 = const_cast<Token*>(TokenList::isFunctionHead(tok, ";{"));\n'
    b'    if (tok2 && tok->next() != tok2) {\n'
    b'        // A requires-clause scan can reach a constructor body past its\n'
    b'        // initializer list. Let ordinary AST construction handle that list.\n'
    b'        for (Token *scan = tok->next(); precedes(scan, tok2); scan = scan->next()) {\n'
    b'            if (scan->str() == ":")\n'
    b'                return nullptr;\n'
    b'            if (Token::Match(scan, "<|[|(|{")) {\n'
    b'                if (!scan->link())\n'
    b'                    return tok2;\n'
    b'                scan = scan->link();\n'
    b'            }\n'
    b'        }\n'
    b'        return tok2;\n'
    b'    }\n'
)


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw,
                        usedforsecurity=False).hexdigest()


def patched_bytes(raw: bytes) -> bytes:
    if not isinstance(raw, bytes) or len(raw) > SOURCE_LIMIT or git_blob(raw) != UPSTREAM_BLOB:
        raise ValueError('upstream_source_mismatch')
    if raw.count(ANCHOR) != 1 or raw.count(METHOD_ANCHOR) != 1:
        raise ValueError('upstream_anchor_mismatch')
    return raw.replace(ANCHOR, REPLACEMENT, 1).replace(METHOD_ANCHOR, METHOD_REPLACEMENT, 1)


def _read(path: Path) -> tuple[bytes, int]:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > SOURCE_LIMIT:
            raise ValueError('upstream_source_type_invalid')
        with os.fdopen(descriptor, 'rb', closefd=False) as handle:
            raw = handle.read(SOURCE_LIMIT + 1)
        if len(raw) != info.st_size:
            raise ValueError('upstream_source_size_mismatch')
        return raw, stat.S_IMODE(info.st_mode)
    finally:
        os.close(descriptor)


def apply_repair(source: Path) -> dict:
    source = Path(source).absolute()
    if source.parent != source.parent.resolve(strict=True):
        raise ValueError('upstream_source_path_invalid')
    raw, mode = _read(source)
    patched = patched_bytes(raw)
    descriptor, name = tempfile.mkstemp(prefix='.nico-ast-', dir=source.parent)
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
    return {
        'schema': 'nico.cppcheck-tool-repair.v1', 'repair_id': REPAIR_ID,
        'upstream_commit': UPSTREAM_COMMIT, 'source_path': 'lib/tokenlist.cpp',
        'source_before_git_blob': UPSTREAM_BLOB, 'source_after_git_blob': git_blob(patched),
        'source_before_sha256': hashlib.sha256(raw).hexdigest(),
        'source_after_sha256': hashlib.sha256(patched).hexdigest(),
        'repair_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'base_tool_version': '2.17.1', 'native_qualification_completed': False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    arguments = parser.parse_args()
    print(json.dumps(apply_repair(arguments.source), sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
