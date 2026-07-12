from __future__ import annotations

import io
import time
import tokenize
from collections import Counter
from pathlib import Path
from typing import Any

import nico.assessment_score_integrity as integrity


BUILTIN_STATIC_CONTEXT_VERSION = "nico-builtin-static-code-context-v3"
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
NON_PRODUCTION_FILE_LIMIT = 1_000
NON_PRODUCTION_BYTE_LIMIT = 10_000_000

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


def _bounded_non_production_files(root: Path) -> tuple[list[Path], list[str]]:
    """Collect non-production source evidence independently from production bounds.

    The main bounded collector can evolve to exclude test and documentation paths.
    Non-production evidence therefore uses its own strict file and byte limits so an
    unsafe example remains disclosed without re-entering production scoring.
    """

    selected: list[Path] = []
    notes: list[str] = []
    total = 0
    for path in root.rglob("*"):
        if len(selected) >= NON_PRODUCTION_FILE_LIMIT:
            notes.append(f"Non-production evidence scan stopped after {NON_PRODUCTION_FILE_LIMIT} source files.")
            break
        if not path.is_file() or path.is_symlink() or path.suffix.lower() not in integrity.SOURCE_SUFFIXES:
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if any(part in integrity.SKIP_PARTS for part in relative.parts):
            continue
        if not _non_production(path, root):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > integrity.MAX_BUILTIN_FILE_BYTES:
            continue
        if total + size > NON_PRODUCTION_BYTE_LIMIT:
            notes.append(f"Non-production evidence scan stopped after {NON_PRODUCTION_BYTE_LIMIT} readable bytes.")
            break
        total += size
        selected.append(path)
    return selected, notes


def _record_hits(
    path: Path,
    root: Path,
    text: str,
    *,
    excluded: bool,
    findings: list[str],
    by_rule: Counter[str],
    seen: set[tuple[str, int, str]],
) -> None:
    relative = path.relative_to(root).as_posix()
    scan_text = text if excluded else _code_only(path, text)
    for line_number, line in enumerate(scan_text.splitlines(), 1):
        for name, pattern, message in integrity.RISK_PATTERNS:
            if not pattern.search(line):
                continue
            key = (relative, line_number, name)
            if key in seen:
                continue
            seen.add(key)
            by_rule[name] += 1
            if len(findings) < 100:
                findings.append(f"{relative}:{line_number}: {name} — {message}")


def triaged_builtin_static_scan(repo_path: Path) -> dict[str, Any]:
    """Scan production executable code while disclosing non-production examples."""

    started = time.monotonic()
    bounded_paths, notes = integrity._bounded_files(repo_path, source_only=True)
    non_production_paths, non_production_notes = _bounded_non_production_files(repo_path)
    production_paths = [path for path in bounded_paths if not _non_production(path, repo_path)]

    material_findings: list[str] = []
    excluded_findings: list[str] = []
    material_by_rule: Counter[str] = Counter()
    excluded_by_rule: Counter[str] = Counter()
    material_seen: set[tuple[str, int, str]] = set()
    excluded_seen: set[tuple[str, int, str]] = set()

    for path in production_paths:
        text = integrity._read_text(path)
        if text is not None:
            _record_hits(path, repo_path, text, excluded=False, findings=material_findings, by_rule=material_by_rule, seen=material_seen)

    for path in non_production_paths:
        text = integrity._read_text(path)
        if text is not None:
            _record_hits(path, repo_path, text, excluded=True, findings=excluded_findings, by_rule=excluded_by_rule, seen=excluded_seen)

    material_count = sum(material_by_rule.values())
    excluded_count = sum(excluded_by_rule.values())
    total_files = len(production_paths) + len(non_production_paths)
    status = "failed" if material_count else "passed"
    summary = (
        f"NICO current-tree static risk scanner inspected {total_files} source file(s): "
        f"production={len(production_paths)}, non-production={len(non_production_paths)}, "
        f"material production hits={material_count}, excluded non-production hits={excluded_count}."
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
        "unavailable_data_notes": notes + non_production_notes + [
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
        "files_scanned": total_files,
        "production_files_scanned": len(production_paths),
        "non_production_files_scanned": len(non_production_paths),
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
        "rule": "Only executable-code-context hits in production paths count as material built-in static findings; independently bounded non-production paths remain disclosed but non-scoring.",
    }


__all__ = [
    "BUILTIN_STATIC_CONTEXT_VERSION",
    "NON_PRODUCTION_PATH_PARTS",
    "install_builtin_static_code_context",
    "triaged_builtin_static_scan",
]
