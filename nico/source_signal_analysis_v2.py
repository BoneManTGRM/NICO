from __future__ import annotations

import ast
import re
from pathlib import PurePosixPath
from typing import Any, Mapping

VERSION = "nico.source-signal-analysis.v2"

_SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
_NON_PRODUCTION_PARTS = {
    "test",
    "tests",
    "fixture",
    "fixtures",
    "example",
    "examples",
    "sample",
    "samples",
    "generated",
    "vendor",
    "vendors",
    "dist",
    "build",
    "coverage",
    "audit-results",
}
_EXAMPLE_ENV_NAMES = {".env.example", ".env.sample", "example.env", "sample.env", "env.example", "env.sample"}
_SECRET_PATTERNS = (
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("generic_secret_assignment", re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=:-]{16,}")),
)
_EXAMPLE_CONNECTION_ASSIGNMENT = re.compile(
    r"(?i)\b[A-Za-z][A-Za-z0-9_]*(?:URL|URI)\s*=\s*[^\s'\"]+://[^\s'\"]+"
)
_JS_RISKS = (
    ("js_inner_html", re.compile(r"\.innerHTML\s*="), "innerHTML assignments can create XSS risk."),
    ("react_dangerous_html", re.compile(r"\bdangerouslySetInnerHTML\b"), "dangerouslySetInnerHTML requires strict sanitization evidence."),
    ("tls_verify_disabled", re.compile(r"\brejectUnauthorized\s*:\s*false\b", re.I), "Disabled TLS verification should not ship to production."),
    ("javascript_eval", re.compile(r"\beval\s*\("), "Dynamic code execution should be reviewed."),
    ("javascript_new_function", re.compile(r"\bnew\s+Function\s*\("), "Dynamic Function construction should be reviewed."),
)
_PLACEHOLDER_MARKERS = (
    "user:password",
    "username:password",
    "changeme",
    "change-me",
    "example",
    "localhost",
    "127.0.0.1",
    "generate-a-long-random-secret",
    "replace-me",
    "replace_me",
    "your_",
    "your-",
    "dummy",
    "placeholder",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _non_production(path: str) -> bool:
    normalized = path.replace("\\", "/")
    parts = [part.casefold() for part in PurePosixPath(normalized).parts]
    name = parts[-1] if parts else ""
    return bool(
        any(part in _NON_PRODUCTION_PARTS for part in parts)
        or name.startswith("test_")
        or name.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
    )


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _source_line(text: str, line: int) -> str:
    lines = text.splitlines()
    return lines[line - 1].strip()[:500] if 1 <= line <= len(lines) else ""


def _python_risks(path: str, text: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError:
        return []
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        rule = ""
        message = ""
        if name in {"eval", "exec"}:
            rule = "python_eval_exec"
            message = "Dynamic code execution should be reviewed."
        elif name == "os.system":
            rule = "python_os_system"
            message = "os.system calls should be replaced with safer subprocess patterns."
        elif name in {"pickle.load", "pickle.loads"}:
            rule = "pickle_loads"
            message = "pickle loading untrusted data can execute code."
        elif name == "yaml.load":
            loaders = {
                _call_name(keyword.value)
                for keyword in node.keywords
                if keyword.arg in {"Loader", "loader"}
            }
            if not any(loader.endswith(("SafeLoader", "CSafeLoader")) for loader in loaders):
                rule = "unsafe_yaml_load"
                message = "yaml.load can be unsafe without SafeLoader."
        elif name.startswith("subprocess."):
            shell_true = any(
                keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
                for keyword in node.keywords
            )
            if shell_true:
                rule = "python_shell_true"
                message = "subprocess shell=True expands command-injection risk."
        elif name.startswith(("requests.", "httpx.")):
            verify_false = any(
                keyword.arg == "verify" and isinstance(keyword.value, ast.Constant) and keyword.value.value is False
                for keyword in node.keywords
            )
            if verify_false:
                rule = "tls_verify_disabled"
                message = "Disabled TLS verification should not ship to production."
        if rule:
            line = int(getattr(node, "lineno", 0) or 0)
            findings.append(
                {
                    "path": path,
                    "line": line,
                    "rule_id": rule,
                    "message": message,
                    "source_excerpt": _source_line(text, line),
                    "analysis_method": "python_ast_executable_call",
                    "production_scope": not _non_production(path),
                }
            )
    return findings


def _strip_js_comments_and_strings(text: str) -> str:
    pattern = re.compile(
        r"(?P<block>/\*.*?\*/)|(?P<line>//[^\n]*)|(?P<string>'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`)",
        re.DOTALL,
    )

    def replacement(match: re.Match[str]) -> str:
        value = match.group(0)
        return "\n" * value.count("\n") if match.group("block") or match.group("string") else ""

    return pattern.sub(replacement, text)


def _javascript_risks(path: str, text: str) -> list[dict[str, Any]]:
    cleaned = _strip_js_comments_and_strings(text)
    lines = cleaned.splitlines()
    original = text.splitlines()
    findings: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        for rule, pattern, message in _JS_RISKS:
            if pattern.search(line):
                excerpt = original[line_number - 1].strip()[:500] if line_number <= len(original) else ""
                findings.append(
                    {
                        "path": path,
                        "line": line_number,
                        "rule_id": rule,
                        "message": message,
                        "source_excerpt": excerpt,
                        "analysis_method": "javascript_lexical_code_only",
                        "production_scope": not _non_production(path),
                    }
                )
    return findings


def _masked(value: str) -> str:
    return "***" if len(value) <= 8 else f"{value[:4]}...{value[-4:]}"


def _is_example_placeholder_line(path: str, line: str) -> bool:
    return bool(
        PurePosixPath(path).name.casefold() in _EXAMPLE_ENV_NAMES
        and any(marker in line.casefold() for marker in _PLACEHOLDER_MARKERS)
    )


def analyze_source_signals(files: Mapping[str, str]) -> dict[str, Any]:
    """Analyze source semantics without promoting comments, strings, or fixtures.

    All observations remain retained. Only executable first-party source findings enter
    the production-risk population.
    """

    todos: list[str] = []
    production_risks: list[str] = []
    production_records: list[dict[str, Any]] = []
    excluded_risks: list[dict[str, Any]] = []
    secrets: list[str] = []
    placeholder_secrets: list[str] = []
    test_paths = [path for path in files if _non_production(path)]
    docs = [path for path in files if path.casefold().endswith(".md") or path.startswith("docs/")]

    for path, text in files.items():
        for line_number, line in enumerate(text.splitlines(), 1):
            upper = line.strip().upper()
            if "TODO" in upper or "FIXME" in upper or "SECURITY" in upper:
                todos.append(f"{path}:{line_number}: {line.strip()[:140]}")
            placeholder_line = _is_example_placeholder_line(path, line)
            matched_secret_pattern = False
            for name, pattern in _SECRET_PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue
                matched_secret_pattern = True
                evidence = f"{path}:{line_number}: potential {name} evidence {_masked(match.group(0))}"
                if placeholder_line:
                    placeholder_secrets.append(evidence)
                elif not _non_production(path):
                    secrets.append(evidence)
            if (
                placeholder_line
                and not matched_secret_pattern
                and _EXAMPLE_CONNECTION_ASSIGNMENT.search(line)
            ):
                placeholder_secrets.append(
                    f"{path}:{line_number}: verified example connection placeholder"
                )

        suffix = PurePosixPath(path).suffix.casefold()
        if suffix not in _SOURCE_SUFFIXES:
            continue
        records = _python_risks(path, text) if suffix == ".py" else _javascript_risks(path, text)
        for record in records:
            rendered = f"{record['path']}:{record['line']}: {record['rule_id']} — {record['message']}"
            if record.get("production_scope") is True:
                production_risks.append(rendered)
                production_records.append(record)
            else:
                excluded_risks.append(record)

    return {
        "todos": todos,
        "risks": production_risks,
        "risk_records": production_records,
        "excluded_non_production_risks": excluded_risks,
        "secrets": secrets,
        "verified_example_placeholder_secrets": placeholder_secrets,
        "test_paths": test_paths,
        "docs": docs,
        "analysis_version": VERSION,
        "executable_source_only": True,
        "comments_and_strings_excluded": True,
        "non_production_findings_retained_separately": True,
    }


__all__ = ["VERSION", "analyze_source_signals"]
