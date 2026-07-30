from __future__ import annotations

import re
from pathlib import Path

ROOTS = (Path("apps"),)
EXCLUDED = {"node_modules", ".next", "dist", "build", "coverage", "generated", "vendor"}
PATTERNS = (
    (re.compile(r"\brejectUnauthorized\s*:\s*false\b"), "TLS certificate verification disabled"),
    (re.compile(r"\bNODE_TLS_REJECT_UNAUTHORIZED\s*=\s*['\"]?0"), "Node TLS verification disabled"),
    (re.compile(r"\bdangerouslyAllowBrowser\s*:\s*true\b"), "browser-side privileged SDK mode enabled"),
)


def test_frontend_sources_do_not_disable_transport_security() -> None:
    violations: list[str] = []
    for root in ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
                continue
            if any(segment in EXCLUDED for segment in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for pattern, description in PATTERNS:
                for match in pattern.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    violations.append(f"{path}:{line}: {description}")

    assert not violations, "\n".join(violations)
