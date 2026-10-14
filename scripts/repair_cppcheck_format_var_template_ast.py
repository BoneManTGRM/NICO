"""Package the existing format-variable-template candidate with a pinned receipt.

This applies the existing candidate, not a newly qualified parser correction.
The emitted receipt explicitly leaves native qualification incomplete.
Assessed source is never modified by this build-time toolchain operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

if __package__:
    from . import repair_cppcheck_placement_ast as placement
else:
    import repair_cppcheck_placement_ast as placement

REPAIR_ID = 'format-var-template-ast-v1'
UPSTREAM_COMMIT = 'ac9db3069b9f90e81e126a090b99ad456e122cf8'

OLD = (
    b'            if (!tok->astOperand1() || !tok->astOperand2())\n'
    b'                throw InternalError(tok, "Syntax Error: AST broken, binary operator \'" + tok->str() + "\' doesn\'t have two operands.", InternalError::AST);\n'
)
NEW = (
    b'            // A linked ">" is a template closing bracket, not a binary operator.\n'
    b'            if (tok->str() == ">" && tok->link())\n'
    b'                continue;\n'
    b'            if (!tok->astOperand1() || !tok->astOperand2())\n'
    b'                throw InternalError(tok, "Syntax Error: AST broken, binary operator \'" + tok->str() + "\' doesn\'t have two operands.", InternalError::AST);\n'
)


def patched_bytes(raw: bytes) -> bytes:
    """Accept only the exact pinned upstream file after the placement repair."""
    if not isinstance(raw, bytes) or len(raw) > placement.SOURCE_LIMIT:
        raise ValueError('upstream_source_mismatch')
    if NEW in raw:
        raise ValueError('format_repair_already_applied')
    if raw.count(OLD) != 1:
        raise ValueError('operand_check_anchor_mismatch')
    if raw.count(placement.REPLACEMENT) != 1:
        raise ValueError('prerequisite_repair_mismatch')
    original = raw.replace(placement.REPLACEMENT, placement.ANCHOR, 1)
    if placement.UPSTREAM_COMMIT != UPSTREAM_COMMIT or placement.patched_bytes(original) != raw:
        raise ValueError('upstream_source_mismatch')
    return raw.replace(OLD, NEW, 1)


def apply(root: Path) -> dict:
    """Apply once and return mechanically verified, explicitly unqualified metadata."""
    target = (Path(root) / 'lib' / 'tokenlist.cpp').absolute()
    if target.parent != target.parent.resolve(strict=True):
        raise ValueError('upstream_source_path_invalid')
    # Reuse the existing pinned repair's bounded, no-symlink file reader.
    raw, mode = placement._read(target)
    patched = patched_bytes(raw)
    descriptor, temporary = tempfile.mkstemp(prefix='.nico-format-', dir=target.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(patched)
            handle.flush()
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        if placement._read(target)[0] != raw:
            raise ValueError('upstream_source_changed')
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {
        'schema': 'nico.cppcheck-tool-repair.v1',
        'repair_id': REPAIR_ID,
        'prerequisite_repair_id': placement.REPAIR_ID,
        'upstream_commit': UPSTREAM_COMMIT,
        'source_path': 'lib/tokenlist.cpp',
        'source_before_git_blob': placement.git_blob(raw),
        'source_after_git_blob': placement.git_blob(patched),
        'source_before_sha256': hashlib.sha256(raw).hexdigest(),
        'source_after_sha256': hashlib.sha256(patched).hexdigest(),
        'repair_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'prerequisite_repair_script_sha256': hashlib.sha256(Path(placement.__file__).read_bytes()).hexdigest(),
        'base_tool_version': '2.17.1',
        'native_qualification_completed': False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, nargs='?', default=Path('.'))
    arguments = parser.parse_args()
    print(json.dumps(apply(arguments.root), sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
