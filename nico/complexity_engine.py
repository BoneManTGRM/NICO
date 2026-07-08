from __future__ import annotations

import ast
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from nico.worker_execution import WorkerLimits, run_command

SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx"}
SKIP_DIRS = {".git", "node_modules", ".next", "dist", "build", ".venv", "venv", "__pycache__", ".pytest_cache"}
BRANCH_RE = re.compile(r"\b(if|elif|else if|for|while|case|catch|except|&&|\|\||\?)\b")
FUNC_RE = re.compile(r"\b(function\s+[A-Za-z_$][\w$]*|const\s+[A-Za-z_$][\w$]*\s*=\s*(?:async\s*)?\(|[A-Za-z_$][\w$]*\s*=>)")
IMPORT_RE = re.compile(r"^\s*(?:import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]|import\s+['\"]([^'\"]+)['\"]|const\s+.*?=\s+require\(['\"]([^'\"]+)['\"]\))", re.MULTILINE)
CALL_RE = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\(")


def _is_source(path: Path) -> bool:
    if path.suffix not in SOURCE_SUFFIXES:
        return False
    return not any(part in SKIP_DIRS for part in path.parts)


def _iter_source_files(repo_dir: Path) -> list[Path]:
    if not repo_dir.exists():
        return []
    return sorted(path for path in repo_dir.rglob("*") if path.is_file() and _is_source(path.relative_to(repo_dir)))


def _safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _python_import_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Import) and node.names:
        return node.names[0].name.split(".", 1)[0]
    if isinstance(node, ast.ImportFrom) and node.module:
        return node.module.split(".", 1)[0]
    return None


def _python_call_name(node: ast.Call) -> str | None:
    target = node.func
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def _python_cyclomatic(tree: ast.AST) -> int:
    complexity = 1
    branch_nodes = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.ExceptHandler, ast.IfExp, ast.BoolOp, ast.Match)
    for node in ast.walk(tree):
        if isinstance(node, branch_nodes):
            complexity += 1
    return complexity


def _analyze_python(path: Path, text: str) -> dict[str, Any]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return {
            "path": str(path),
            "loc": len(text.splitlines()),
            "function_count": 0,
            "class_count": 0,
            "cyclomatic_complexity": 0,
            "imports": [],
            "calls": [],
            "parse_error": f"Python parse error: {exc.msg}",
        }

    imports: list[str] = []
    calls: list[str] = []
    function_count = 0
    class_count = 0
    max_function_complexity = 0
    for node in ast.walk(tree):
        import_name = _python_import_name(node)
        if import_name:
            imports.append(import_name)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_count += 1
            max_function_complexity = max(max_function_complexity, _python_cyclomatic(node))
        elif isinstance(node, ast.ClassDef):
            class_count += 1
        elif isinstance(node, ast.Call):
            call_name = _python_call_name(node)
            if call_name:
                calls.append(call_name)

    return {
        "path": str(path),
        "loc": len([line for line in text.splitlines() if line.strip()]),
        "function_count": function_count,
        "class_count": class_count,
        "cyclomatic_complexity": _python_cyclomatic(tree),
        "max_function_complexity": max_function_complexity,
        "imports": sorted(set(imports)),
        "calls": sorted(set(calls)),
    }


def _analyze_script(path: Path, text: str) -> dict[str, Any]:
    imports = sorted({match.group(1) or match.group(2) or match.group(3) for match in IMPORT_RE.finditer(text) if match.group(1) or match.group(2) or match.group(3)})
    calls = sorted({match.group(1) for match in CALL_RE.finditer(text) if match.group(1) not in {"if", "for", "while", "switch", "catch", "function", "return"}})
    return {
        "path": str(path),
        "loc": len([line for line in text.splitlines() if line.strip()]),
        "function_count": len(FUNC_RE.findall(text)),
        "class_count": len(re.findall(r"\bclass\s+[A-Za-z_$][\w$]*", text)),
        "cyclomatic_complexity": 1 + len(BRANCH_RE.findall(text)),
        "max_function_complexity": 0,
        "imports": imports,
        "calls": calls[:80],
    }


def _analyze_file(repo_dir: Path, path: Path) -> dict[str, Any]:
    rel = path.relative_to(repo_dir)
    text = _safe_read(path)
    if path.suffix == ".py":
        return _analyze_python(rel, text)
    return _analyze_script(rel, text)


def _git_numstat(repo_dir: Path) -> dict[str, int]:
    result = run_command(("git", "log", "--numstat", "--pretty=format:"), cwd=repo_dir, limits=WorkerLimits(timeout_seconds=45, max_output_chars=120_000))
    if not result.ok:
        return {}
    churn: dict[str, int] = defaultdict(int)
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        try:
            churn[path] += int(added if added.isdigit() else 0) + int(deleted if deleted.isdigit() else 0)
        except ValueError:
            continue
    return dict(churn)


def _git_owners(repo_dir: Path) -> tuple[dict[str, str], dict[str, float]]:
    result = run_command(("git", "log", "--format=author:%ae", "--name-only"), cwd=repo_dir, limits=WorkerLimits(timeout_seconds=45, max_output_chars=120_000))
    if not result.ok:
        return {}, {}
    current_author = "unknown"
    file_authors: dict[str, Counter[str]] = defaultdict(Counter)
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("author:"):
            current_author = line.split(":", 1)[1] or "unknown"
            continue
        file_authors[line][current_author] += 1
    owners: dict[str, str] = {}
    concentration: dict[str, float] = {}
    for path, counts in file_authors.items():
        total = sum(counts.values())
        if not total:
            continue
        owner, owner_count = counts.most_common(1)[0]
        owners[path] = owner
        concentration[path] = round(owner_count / total, 2)
    return owners, concentration


def _manifest_dependency_count(repo_dir: Path) -> int:
    count = 0
    requirements = repo_dir / "requirements.txt"
    if requirements.exists():
        for line in _safe_read(requirements).splitlines():
            raw = line.strip()
            if raw and not raw.startswith("#") and not raw.startswith("-"):
                count += 1
    for package_json in repo_dir.glob("**/package.json"):
        if any(part in SKIP_DIRS for part in package_json.relative_to(repo_dir).parts):
            continue
        try:
            data = json.loads(_safe_read(package_json))
        except ValueError:
            continue
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            section = data.get(key)
            if isinstance(section, dict):
                count += len(section)
    return count


def _external_imports(file_metrics: list[dict[str, Any]]) -> Counter[str]:
    imports: Counter[str] = Counter()
    for item in file_metrics:
        for name in item.get("imports", []):
            if not isinstance(name, str) or name.startswith((".", "nico", "apps", "tests")):
                continue
            imports[name.split("/", 1)[0]] += 1
    return imports


def _score_profile(file_metrics: list[dict[str, Any]], churn: dict[str, int], owner_concentration: dict[str, float], manifest_dependency_count: int) -> tuple[int, str, list[str]]:
    findings: list[str] = []
    source_count = len(file_metrics)
    total_loc = sum(int(item.get("loc") or 0) for item in file_metrics)
    max_complexity = max([int(item.get("cyclomatic_complexity") or 0) for item in file_metrics] or [0])
    high_complexity_files = [item for item in file_metrics if int(item.get("cyclomatic_complexity") or 0) >= 35]
    high_churn_files = [path for path, value in churn.items() if value >= 500]
    concentrated_files = [path for path, value in owner_concentration.items() if value >= 0.9]

    score = 88
    if source_count > 250:
        score -= 10
        findings.append("Source-file footprint is large and should be reviewed for modularity boundaries.")
    elif source_count > 120:
        score -= 4
    if total_loc > 50_000:
        score -= 8
        findings.append("Total source LOC is high for an Express review and increases architecture review depth.")
    if max_complexity >= 60:
        score -= 15
        findings.append("At least one file has very high estimated cyclomatic complexity.")
    elif max_complexity >= 35:
        score -= 8
        findings.append("At least one file has elevated estimated cyclomatic complexity.")
    if len(high_complexity_files) >= 5:
        score -= 6
        findings.append("Multiple files have elevated complexity and should be decomposed or tested more heavily.")
    if len(high_churn_files) >= 5:
        score -= 6
        findings.append("Several files show high churn and should be treated as delivery hotspots.")
    if len(concentrated_files) >= max(3, source_count // 8):
        score -= 5
        findings.append("Ownership concentration is high enough to create maintenance risk if reviewers are unavailable.")
    if manifest_dependency_count > 120:
        score -= 5
        findings.append("Manifest dependency count is high enough to raise dependency-surface review priority.")

    risk_level = "low"
    if score < 70:
        risk_level = "high"
    elif score < 82:
        risk_level = "medium"
    return max(35, min(96, score)), risk_level, findings


def build_complexity_profile(repo_dir: Path | str) -> dict[str, Any]:
    repo_path = Path(repo_dir).resolve()
    source_files = _iter_source_files(repo_path)
    file_metrics = [_analyze_file(repo_path, path) for path in source_files]
    churn = _git_numstat(repo_path)
    owners, owner_concentration = _git_owners(repo_path)
    manifest_dependency_count = _manifest_dependency_count(repo_path)
    external_imports = _external_imports(file_metrics)

    incoming: Counter[str] = Counter()
    for item in file_metrics:
        for call in item.get("calls", []):
            incoming[str(call)] += 1

    for item in file_metrics:
        path = str(item["path"])
        item["churn"] = churn.get(path, 0)
        item["primary_owner"] = owners.get(path, "unknown")
        item["owner_concentration"] = owner_concentration.get(path, 0)
        item["hotspot_score"] = round(
            int(item.get("cyclomatic_complexity") or 0) * 2
            + int(item.get("loc") or 0) / 75
            + int(item.get("churn") or 0) / 60,
            2,
        )

    hotspots = sorted(file_metrics, key=lambda item: item.get("hotspot_score", 0), reverse=True)[:12]
    call_edge_count = sum(len(item.get("calls", [])) for item in file_metrics)
    total_loc = sum(int(item.get("loc") or 0) for item in file_metrics)
    total_functions = sum(int(item.get("function_count") or 0) for item in file_metrics)
    max_complexity = max([int(item.get("cyclomatic_complexity") or 0) for item in file_metrics] or [0])
    complexity_score, risk_level, findings = _score_profile(file_metrics, churn, owner_concentration, manifest_dependency_count)

    evidence = [
        f"Complexity engine analyzed {len(file_metrics)} source file(s), {total_loc} source LOC, and {total_functions} function-like units.",
        f"Estimated call graph edges: {call_edge_count}; max file cyclomatic complexity: {max_complexity}.",
        f"Hotspot candidates identified: {len(hotspots)}; manifest dependency count: {manifest_dependency_count}.",
    ]
    if churn:
        evidence.append(f"Git churn data available for {len(churn)} file(s).")
    else:
        evidence.append("Git churn data unavailable or empty for this checkout.")
    if owners:
        evidence.append(f"Ownership signal available for {len(owners)} file(s).")
    else:
        evidence.append("Ownership signal unavailable or empty for this checkout.")

    return {
        "artifact_schema": "nico.complexity.v1",
        "source_file_count": len(file_metrics),
        "analyzed_file_count": len(file_metrics),
        "total_loc": total_loc,
        "total_functions": total_functions,
        "call_graph_edge_count": call_edge_count,
        "max_file_cyclomatic_complexity": max_complexity,
        "average_cyclomatic_per_file": round(sum(int(item.get("cyclomatic_complexity") or 0) for item in file_metrics) / max(1, len(file_metrics)), 2),
        "manifest_dependency_count": manifest_dependency_count,
        "external_import_count": sum(external_imports.values()),
        "top_external_imports": external_imports.most_common(12),
        "hotspots": [
            {
                "path": item.get("path"),
                "hotspot_score": item.get("hotspot_score"),
                "loc": item.get("loc"),
                "cyclomatic_complexity": item.get("cyclomatic_complexity"),
                "churn": item.get("churn"),
                "primary_owner": item.get("primary_owner"),
                "owner_concentration": item.get("owner_concentration"),
            }
            for item in hotspots
        ],
        "churn": {
            "files_with_churn": len(churn),
            "top_churn_files": sorted(churn.items(), key=lambda item: item[1], reverse=True)[:12],
        },
        "ownership": {
            "files_with_owner_signal": len(owners),
            "high_concentration_files": sorted(
                [(path, value) for path, value in owner_concentration.items() if value >= 0.9],
                key=lambda item: item[1],
                reverse=True,
            )[:12],
        },
        "complexity_score": complexity_score,
        "architecture_score": max(45, min(94, complexity_score + 2)),
        "velocity_score": max(45, min(92, complexity_score)),
        "risk_level": risk_level,
        "evidence": evidence,
        "findings": findings,
        "unavailable": [],
        "human_review_required": True,
    }
