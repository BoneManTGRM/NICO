"""Pinned Cppcheck AST repair for variable-template specializations.

Fixes internalAstError on GCC <format> line 299:
  static constexpr bool __is_specialization_of<_Class<_Args...>, _Class> = true;

The closing '>' of a template specialization must be linked as a bracket
before the binary-operator two-operand check. Genuine comparison operators
remain validated. Assessed sources and required checks are unchanged.
"""
from __future__ import annotations

from pathlib import Path

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

def apply(root: Path) -> None:
    target = root / 'lib' / 'tokenlist.cpp'
    raw = target.read_bytes()
    if OLD not in raw:
        raise SystemExit('expected operand-check pattern not found')
    if raw.count(OLD) != 1:
        raise SystemExit('operand-check pattern not unique')
    target.write_bytes(raw.replace(OLD, NEW, 1))
    print(f'{REPAIR_ID} applied to {target}')

if __name__ == '__main__':
    import sys
    apply(Path(sys.argv[1] if len(sys.argv) > 1 else '.'))
