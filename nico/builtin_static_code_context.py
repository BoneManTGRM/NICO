from __future__ import annotations

import io
import time
import tokenize
from collections import Counter
from pathlib import Path
from typing import Any

import nico.assessment_score_integrity as integrity


BUILTIN_STATIC_CONTEXT_VERSION = "nico-builtin-static-code-context-v2"
NON_PRODUCTION_PATH_PARTS = {
    "test",
    "tests",
    "fixture",
    "fixtures",
    "example",
    "examples",
    "sample",
    "samples",
    "docs",
    "documentation",
}

_ORIGINAL_BUILTIN_STATIC_SCAN = integrity._built_in_static_scan


def _blank(value: str) -> str:
    return "".join("\n" if character == "\n" else " " for character in value)


def _mask_python_comments_and_strings(text: str) -> str:
    try:
        tokens: list[tokenize.TokenInfo] = []
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type in {tokenize.STRING, tokenize.COMMENT}:
                token = tokenize.TokenInfo(token.type, _blank(token.string), token.start, token.end, token.line)
            tokens.append(token)
        return tokenize.untokenize(tokens)
    except (IndentationError, SyntaxError, tokenize.TokenError):
        return _mask_generic_comments_and_strings(text)


def _mask_generic_comments_and_strings(text: str) -> str:
    characters = list(text)
    index = 0
    state = "code"
    quote = ""
    while index < len(characters):
        current = characters[index]
        following = characters[index + 1] if index + 1 < len(characters) else ""
        if state == "code":
            if current == "#":
                characters[index] = " "
                state = "line_comment"
            elif current == "/" and following == "/":
                characters[index] = characters[index + 1] = " "
                index += 1
                state = "line_comment"
            elif current == "/" and following == "*":
                characters[index] = characters[index + 1] = " "
                index += 1
                state = "block_comment"
            elif current in {"'", '"', "`"}:
                quote = current
                characters[index] = " "
                state = "string"
        elif state == "line_comment":
            if current == "\n":
                state = "code"
            else:
                characters[index] = " "
        elif state == "block_comment":
            if current == "*" and following == "/":
                characters[index] = characters[index + 1] = " "
                index += 1
                state = "code"
            elif current != "\n":
                characters[index] = " "
        elif state == "string":
            if current == "\\":
                characters[index] = " "
                if index + 1 < len(characters) and characters[index + 1] != "\n":
                    characters[index + 1] = " "
                    index += 1
            elif current == quote:
                characters[index] = " "
                state = "code"
            elif current != "\n":
                characters[index] = " "
        index += 1
    return "".join(characters)


def _code_only(path: Path, text: str) -> str:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return _mask_python_comments_and_strings(text)
    if suffix in {".js", ".jsx", ".ts", ".tsx"}:
        return integrity._mask_js_comments_and_strings(text)
    return _mask_generic_comments_and_strings(text)


def _non_production(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    parts = {part.lower() for part in relative.parts}
    name = relative.name.lower()
    return bool(parts & NON_PRODUCTION_PATH_PARTS) or name.startswith(("test_", "spec_")) or name.endswith(("_test.py", ".test.js", ".test.ts", ".test.tsx", ".spec.js", ".spec.ts", ".spec.tsx"))


def triaged_builtin_static_scan(repo_path: Path) -> dict[str, Any]:
    """Scan production executable code while disclosing non-production examples.

    Production paths are matched only after comments and string literals are masked.
    Test, fixture, example, sample, and documentation paths are non-scoring evidence;
    their raw pattern matches are disclosed so intentionally unsafe examples are not
    lost while they remain incapable of lowering the production score.
    """

    started = time.monotonic()
    paths, notes = integrity._bounded_files(repo_path, source_only=True)
    material_findings: list[str] = []
    excluded_findings: list[str] = []
    material_by_rule: Counter[str] = Counter()
    excluded_by_rule: Counter[str] = Counter()
    material_seen: set[tuple[str, int, str]] = set()
    excluded_seen: set[tuple[str, int, str]] = set()

    for path in paths:
        text = integrity._read_text(path)
        if text is None:
            continue
        relative = path.relative_to(repo_path).as_posix()
        excluded_path = _non_production(path, repo_path)
        scan_text = text if excluded_path else _code_only(path, text)
        for line_number, line in enumerate(scan_text.splitlines(), 1):
            for name, pattern, message in integrity.RISK_PATTERNS:
                if not pattern.search(line):
                    continue
                key = (relative, line_number, name)
                finding = f"{relative}:{line_number}: {name} — {message}"
                if excluded_path:
                    if key in excluded_seen:
                        continue
                    excluded_seen.add(key)
                    excluded_by_rule[name] += 1
                    if len(excluded_findings) < 100:
                        excluded_findings.append(finding)
                else:
                    if key in material_seen:
                        continue
                    material_seen.add(key)
                    material_by_rule[name] += 1
                    if len(material_findings) < 100:
                        material_findings.append(finding)

    material_count = sum(material_by_rule.values())
    excluded_count = sum(excluded_by_rule.values())
    status = "failed" if material_count else "passed"
    summary = (
        f"NICO current-tree static risk scanner inspected {len(paths)} source file(s): "
        f"material production hits={material_count}; excluded non-production hits={excluded_count}."
    )
    preview_lines = material_findings[:30]
    if not preview_lines and excluded_count:
        preview_lines = [f"Excluded non-production findings: {excluded_count}."]

    return {
        "scanner": "nico-static",
        "command_intent": "Bounded current-tree executable-code static risk review",
        "status": status,
        "exit_code": 1 if material_count else 0,
        "duration_seconds": round(time.monotonic() - started, 2),
        "evidence_summary": summary,
        "safe_output_preview": "\n".join(preview_lines),
        "risk_severity": "high" if material_count else "low",
        "recommended_repair": "Review each material production hit and confirm exploitability before repair prioritization.",
        "unavailable_data_notes": notes + [
            "Production comments, string literals, and detector definitions are excluded from material matching.",
            "Raw pattern matches under tests, fixtures, examples, samples, and documentation are disclosed separately and never lower the production score.",
            "Built-in pattern coverage does not replace language-specific semantic analyzers.",
        ],
        "secret_redaction_applied": False,
        "finding_count": material_count,
        "material_finding_count": material_count,
        "review_finding_count": 0,
        "test_only_finding_count": excluded_count,
        "total_finding_count": material_count + excluded_count,
        "findings_by_rule": dict(sorted(material_by_rule.items())),
        "excluded_findings_by_rule": dict(sorted(excluded_by_rule.items())),
        "files_scanned": len(paths),
        "analyzer_version": BUILTIN_STATIC_CONTEXT_VERSION,
        "code_context_masking": True,
    }


def install_builtin_static_code_context() -> dict[str, Any]:
    installed = bool(getattr(integrity, "_nico_builtin_static_code_context_installed", False))
    integrity._built_in_static_scan = triaged_builtin_static_scan
    integrity._nico_builtin_static_code_context_installed = True
    return {
        "status": "already_installed" if installed else "installed",
        "version": BUILTIN_STATIC_CONTEXT_VERSION,
        "rule": "Only executable-code-context hits in production paths count as material built-in static findings; non-production paths remain disclosed but non-scoring.",
    }


__all__ = [
    "BUILTIN_STATIC_CONTEXT_VERSION",
    "NON_PRODUCTION_PATH_PARTS",
    "install_builtin_static_code_context",
    "triaged_builtin_static_scan",
]
