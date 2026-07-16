from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audit-results" / "system-wide-integrity-audit.json"
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json", ".toml", ".yml", ".yaml", ".sh", ".md"}
SKIP_DIRS = {".git", ".next", "node_modules", ".venv", "venv", "dist", "build", "coverage", "audit-results"}
TEST_MARKERS = {"tests", "test", "fixtures", "fixture", "examples", "example"}
SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|private[_-]?key)\s*[:=]\s*['\"]([^'\"\n]{12,})['\"]"
)
TEMP_PATTERN = re.compile(r"(?i)(temporary|tmp[-_ ]?probe|do[-_ ]?not[-_ ]?use|noop)")


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _is_test_path(path: Path) -> bool:
    return bool(set(part.lower() for part in path.parts) & TEST_MARKERS)


def _finding(kind: str, path: Path, line: int, detail: str, severity: str = "medium") -> dict[str, Any]:
    return {
        "kind": kind,
        "severity": severity,
        "path": _rel(path),
        "line": int(line or 1),
        "detail": " ".join(str(detail).split())[:500],
    }


def _call_name(node: ast.Call) -> str:
    target = node.func
    parts: list[str] = []
    while isinstance(target, ast.Attribute):
        parts.append(target.attr)
        target = target.value
    if isinstance(target, ast.Name):
        parts.append(target.id)
    return ".".join(reversed(parts))


def _literal_truthy(keyword: ast.keyword, expected: bool = True) -> bool:
    return isinstance(keyword.value, ast.Constant) and keyword.value.value is expected


def _python_findings(path: Path, text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    syntax: list[dict[str, Any]] = []
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        syntax.append(_finding("python_syntax_error", path, exc.lineno or 1, exc.msg, "critical"))
        return findings, syntax

    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            body_only_pass = len(node.body) == 1 and isinstance(node.body[0], ast.Pass)
            body_only_continue = len(node.body) == 1 and isinstance(node.body[0], ast.Continue)
            if node.type is None:
                findings.append(_finding("bare_except", path, node.lineno, "Bare except catches BaseException, including cancellation and process-exit signals.", "high"))
            if body_only_pass or body_only_continue:
                caught = "bare" if node.type is None else ast.unparse(node.type)
                findings.append(_finding("swallowed_exception", path, node.lineno, f"{caught} exception is silently discarded.", "high"))

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = list(node.args.defaults) + [item for item in node.args.kw_defaults if item is not None]
            for default in defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    findings.append(_finding("mutable_default_argument", path, node.lineno, f"Function {node.name} has a mutable default argument.", "high"))

        if isinstance(node, ast.Call):
            name = _call_name(node)
            keywords = {item.arg: item for item in node.keywords if item.arg}
            if name in {"eval", "exec", "builtins.eval", "builtins.exec"}:
                findings.append(_finding("dynamic_code_execution", path, node.lineno, f"Call to {name}.", "critical"))
            if name == "os.system":
                findings.append(_finding("os_system", path, node.lineno, "os.system executes through a shell.", "critical"))
            if name.startswith("subprocess."):
                if any(item.arg == "shell" and _literal_truthy(item) for item in node.keywords):
                    findings.append(_finding("subprocess_shell_true", path, node.lineno, f"{name} uses shell=True.", "critical"))
                if name in {"subprocess.run", "subprocess.call", "subprocess.check_call", "subprocess.check_output"} and "timeout" not in keywords:
                    findings.append(_finding("subprocess_without_timeout", path, node.lineno, f"{name} has no explicit timeout.", "medium"))
            if name in {"tempfile.mktemp", "mktemp"}:
                findings.append(_finding("insecure_tempfile", path, node.lineno, f"Call to {name} is race-prone.", "high"))
            if name in {"pickle.load", "pickle.loads", "dill.load", "dill.loads"}:
                findings.append(_finding("unsafe_deserialization", path, node.lineno, f"Call to {name} can execute attacker-controlled payloads.", "critical"))
            if name in {"requests.get", "requests.post", "requests.put", "requests.patch", "requests.delete", "requests.request", "httpx.get", "httpx.post", "httpx.put", "httpx.patch", "httpx.delete", "httpx.request"} and "timeout" not in keywords:
                findings.append(_finding("network_call_without_timeout", path, node.lineno, f"{name} has no explicit timeout.", "high"))
            if name.endswith("decode") and any(item.arg == "options" for item in node.keywords):
                source = ast.get_source_segment(text, node) or ""
                if "verify_signature" in source and "False" in source:
                    findings.append(_finding("jwt_signature_verification_disabled", path, node.lineno, source, "critical"))
            if name in {"requests.get", "requests.post", "requests.request", "httpx.get", "httpx.post", "httpx.request"}:
                if any(item.arg == "verify" and isinstance(item.value, ast.Constant) and item.value.value is False for item in node.keywords):
                    findings.append(_finding("tls_verification_disabled", path, node.lineno, f"{name} uses verify=False.", "critical"))

    return findings, syntax


def _text_findings(path: Path, text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    rel = _rel(path)
    lines = text.splitlines()
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if path.suffix in {".yml", ".yaml"} and ".github/workflows/" in rel:
            if "pull_request_target:" in stripped:
                findings.append(_finding("pull_request_target", path, index, stripped, "critical"))
            if stripped.startswith("permissions:") and "write-all" in stripped:
                findings.append(_finding("workflow_write_all", path, index, stripped, "critical"))
            if "|| true" in line and any(term in line.lower() for term in ("audit", "bandit", "semgrep", "gitleaks", "trufflehog", "osv")):
                findings.append(_finding("security_check_fail_open", path, index, stripped, "high"))
            match = re.search(r"uses:\s*([^\s#]+)", line)
            if match:
                ref = match.group(1)
                if "@" in ref:
                    version = ref.rsplit("@", 1)[1]
                    if not re.fullmatch(r"[0-9a-fA-F]{40}", version):
                        findings.append(_finding("github_action_not_sha_pinned", path, index, ref, "medium"))
        if "allow_origins" in line and "*" in line:
            findings.append(_finding("cors_wildcard", path, index, stripped, "high"))
        if "allow_credentials" in line and "True" in line:
            findings.append(_finding("cors_credentials_enabled", path, index, stripped, "medium"))
        if "os.getenv" in line and re.search(r"(?i)(token|secret|password|key)", line):
            literal = re.search(r"os\.getenv\([^,]+,\s*['\"]([^'\"]+)['\"]", line)
            if literal and literal.group(1).lower() not in {"", "false", "true", "none", "0"}:
                findings.append(_finding("credential_environment_fallback", path, index, stripped, "high"))
        secret = SECRET_PATTERN.search(line)
        if secret and not _is_test_path(path):
            value = secret.group(2)
            if not any(marker in value.lower() for marker in ("example", "placeholder", "replace", "dummy", "test", "redacted", "<")):
                findings.append(_finding("possible_hardcoded_secret", path, index, f"{secret.group(1)} literal length={len(value)}", "critical"))
    return findings


def _run(command: list[str], cwd: Path, timeout: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1"},
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-200000:],
            "stderr": completed.stderr[-50000:],
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": None,
            "stdout": (exc.stdout or "")[-200000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-50000:] if isinstance(exc.stderr, str) else "",
            "timed_out": True,
        }
    except Exception as exc:
        return {
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
            "timed_out": False,
        }


def _json_output(result: dict[str, Any]) -> Any:
    for candidate in (result.get("stdout"), result.get("stderr")):
        try:
            return json.loads(str(candidate or ""))
        except json.JSONDecodeError:
            continue
    return None


def test_temporary_system_integrity_probe() -> None:
    findings: list[dict[str, Any]] = []
    syntax_errors: list[dict[str, Any]] = []
    files_scanned = 0
    python_files = 0
    text_files = 0
    tracked_temp_files: list[str] = []

    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = _rel(path)
        files_scanned += 1
        if TEMP_PATTERN.search(path.name) and not _is_test_path(path):
            tracked_temp_files.append(rel)
            findings.append(_finding("temporary_or_noop_file", path, 1, "Tracked filename looks temporary or no-op.", "medium"))
        if path.suffix not in TEXT_SUFFIXES and path.name not in {"Dockerfile", "Procfile"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        text_files += 1
        if path.suffix == ".py":
            python_files += 1
            py_findings, py_syntax = _python_findings(path, text)
            findings.extend(py_findings)
            syntax_errors.extend(py_syntax)
        findings.extend(_text_findings(path, text))

    commands: dict[str, dict[str, Any]] = {
        "compileall": _run(["python", "-m", "compileall", "-q", "nico", "scripts", "tests"], ROOT, 180),
        "git_diff_check": _run(["git", "diff", "--check", "HEAD"], ROOT, 60),
        "bandit": _run(["python", "-m", "bandit", "-r", "nico", "-f", "json", "-q"], ROOT, 300),
        "pip_audit": _run(["python", "-m", "pip_audit", "--format", "json"], ROOT, 300),
        "npm_audit": _run(["npm", "audit", "--json", "--omit=dev"], ROOT / "apps" / "web", 300),
    }

    bandit_json = _json_output(commands["bandit"])
    bandit_results = bandit_json.get("results", []) if isinstance(bandit_json, dict) else []
    pip_json = _json_output(commands["pip_audit"])
    pip_dependencies = pip_json.get("dependencies", []) if isinstance(pip_json, dict) else []
    pip_vulnerabilities = [
        {"name": item.get("name"), "version": item.get("version"), "vulns": item.get("vulns")}
        for item in pip_dependencies
        if isinstance(item, dict) and item.get("vulns")
    ]
    npm_json = _json_output(commands["npm_audit"])
    npm_metadata = npm_json.get("metadata", {}) if isinstance(npm_json, dict) else {}

    severity_counts: dict[str, int] = {}
    kind_counts: dict[str, int] = {}
    for item in findings + syntax_errors:
        severity_counts[item["severity"]] = severity_counts.get(item["severity"], 0) + 1
        kind_counts[item["kind"]] = kind_counts.get(item["kind"], 0) + 1

    report = {
        "version": "nico.temporary_system_integrity_probe.v1",
        "repository": "BoneManTGRM/NICO",
        "files_scanned": files_scanned,
        "text_files_scanned": text_files,
        "python_files_scanned": python_files,
        "syntax_errors": syntax_errors,
        "static_findings": findings,
        "severity_counts": severity_counts,
        "kind_counts": kind_counts,
        "tracked_temp_files": tracked_temp_files,
        "external_checks": {
            "compileall": commands["compileall"],
            "git_diff_check": commands["git_diff_check"],
            "bandit": {
                "execution": commands["bandit"],
                "metrics": bandit_json.get("metrics", {}) if isinstance(bandit_json, dict) else {},
                "results": bandit_results,
            },
            "pip_audit": {
                "execution": commands["pip_audit"],
                "vulnerabilities": pip_vulnerabilities,
            },
            "npm_audit": {
                "execution": commands["npm_audit"],
                "metadata": npm_metadata,
                "vulnerabilities": npm_json.get("vulnerabilities", {}) if isinstance(npm_json, dict) else {},
            },
        },
        "interpretation": {
            "probe_only": True,
            "automatic_fix_allowed": False,
            "test_and_fixture_findings_require_triage": True,
            "missing_tool_output_is_not_clean_evidence": True,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")

    summary = {
        "files_scanned": files_scanned,
        "python_files": python_files,
        "syntax_errors": len(syntax_errors),
        "static_findings": len(findings),
        "severity_counts": severity_counts,
        "kind_counts": kind_counts,
        "bandit_findings": len(bandit_results),
        "pip_vulnerable_dependencies": len(pip_vulnerabilities),
        "npm_vulnerability_totals": npm_metadata.get("vulnerabilities", {}),
        "compileall_returncode": commands["compileall"]["returncode"],
        "git_diff_check_returncode": commands["git_diff_check"]["returncode"],
        "artifact": "audit-results/system-wide-integrity-audit.json",
    }
    raise AssertionError("NICO_SYSTEM_INTEGRITY_PROBE=" + json.dumps(summary, sort_keys=True))
