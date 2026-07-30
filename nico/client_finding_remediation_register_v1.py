from __future__ import annotations

import hashlib
import html
import io
import re
from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping

VERSION = "nico.client-finding-remediation-register.v1"
MAX_PDF_CODE_FINDINGS = 60
_CODE_SUFFIXES = (".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rb", ".rs", ".cs", ".php", ".swift", ".kt", ".kts")
_NON_PRODUCTION_PARTS = {"test", "tests", "fixture", "fixtures", "example", "examples", "sample", "samples", "generated", "vendor", "vendors", "dist", "build", "coverage"}
_SECRET_TOOLS = {"gitleaks", "trufflehog"}
_SKIP_RECURSIVE_KEYS = {"pdf_base64", "markdown", "html", "raw_output", "stdout", "stderr", "secret", "match"}
_RISK_LINE = re.compile(
    r"(?P<path>[A-Za-z0-9_@./+\-]+\.(?:py|js|jsx|ts|tsx|java|go|rb|rs|cs|php|swift|kt|kts))"
    r":(?P<line>\d+)(?::(?P<column>\d+))?:\s*(?P<rule>[A-Za-z0-9_.\-]+)\s*[—-]\s*(?P<message>.+)",
    re.IGNORECASE,
)
_HOTSPOT_LINE = re.compile(
    r"(?:Actionable\s+hotspot\s+)?(?P<path>[A-Za-z0-9_@./+\-]+\.(?:py|js|jsx|ts|tsx))"
    r":(?P<line>\d+)\s*[·-]\s*(?P<symbol>[^·]+?)\s*[·-]\s*complexity\s+(?P<complexity>\d+)",
    re.IGNORECASE,
)
_SECRET_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{12,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{12,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", re.DOTALL),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)(\s*[:=]\s*)['\"]?[A-Za-z0-9_./+=:\-]{12,}"),
)


def _text(value: Any, limit: int = 6000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _scanner_name(value: Any) -> str:
    normalized = _text(value).casefold().replace("_", "-")
    return {
        "npm audit": "npm-audit",
        "pip audit": "pip-audit",
        "osv": "osv-scanner",
        "tsc": "typescript",
        "truffle-hog": "trufflehog",
    }.get(normalized, normalized)


def _redact(value: Any, limit: int = 1600) -> str:
    text = _text(value, limit * 2)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]" if match.lastindex and match.lastindex >= 2 else "[REDACTED]", text)
    return _text(text, limit)


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _mapping_path(value: Any) -> tuple[str, int | None, int | None, int | None]:
    if isinstance(value, str):
        raw = _text(value).replace("\\", "/")
        match = re.match(r"^(.*?):(\d+)(?::(\d+))?$", raw)
        if match:
            return match.group(1), int(match.group(2)), int(match.group(3)) if match.group(3) else None, None
        return raw, None, None, None
    if not isinstance(value, Mapping):
        return "", None, None, None
    path = _text(_first(value, "path", "file", "file_path", "filename", "filePath", "File")).replace("\\", "/")
    line_raw = _first(value, "line", "start_line", "line_number", "lineNumber", "StartLine")
    column_raw = _first(value, "column", "start_column", "column_number", "columnNumber", "StartColumn")
    end_raw = _first(value, "end_line", "endLine", "EndLine")
    line = int(line_raw) if isinstance(line_raw, (int, float)) or str(line_raw or "").isdigit() else None
    column = int(column_raw) if isinstance(column_raw, (int, float)) or str(column_raw or "").isdigit() else None
    end_line = int(end_raw) if isinstance(end_raw, (int, float)) or str(end_raw or "").isdigit() else None
    return path, line, column, end_line


def _finding_location(finding: Mapping[str, Any]) -> tuple[str, int | None, int | None, int | None]:
    path, line, column, end_line = _mapping_path(finding.get("location"))
    if not path:
        path = _text(
            _first(
                finding,
                "dependency_path",
                "source_path",
                "file_path",
                "filename",
                "path",
                "filePath",
                "File",
                "manifest",
                "lockfile",
            )
        ).replace("\\", "/")
    if line is None:
        raw = _first(finding, "line", "start_line", "line_number", "lineNumber", "StartLine")
        line = int(raw) if isinstance(raw, (int, float)) or str(raw or "").isdigit() else None
    if column is None:
        raw = _first(finding, "column", "start_column", "columnNumber", "StartColumn")
        column = int(raw) if isinstance(raw, (int, float)) or str(raw or "").isdigit() else None
    if end_line is None:
        raw = _first(finding, "end_line", "endLine", "EndLine")
        end_line = int(raw) if isinstance(raw, (int, float)) or str(raw or "").isdigit() else None

    source = finding.get("source")
    if isinstance(source, Mapping) and not path:
        path, source_line, source_column, source_end = _mapping_path(source)
        line = line or source_line
        column = column or source_column
        end_line = end_line or source_end

    metadata = finding.get("SourceMetadata")
    if isinstance(metadata, Mapping):
        data = metadata.get("Data") if isinstance(metadata.get("Data"), Mapping) else {}
        git = data.get("Git") if isinstance(data, Mapping) and isinstance(data.get("Git"), Mapping) else {}
        if not path:
            path = _text(_first(git, "file", "path", "filename")).replace("\\", "/")
        if line is None:
            raw = _first(git, "line", "line_number")
            line = int(raw) if isinstance(raw, (int, float)) or str(raw or "").isdigit() else None
    return path, line, column, end_line


def _location_text(path: str, line: int | None, column: int | None = None, end_line: int | None = None) -> str:
    if not path:
        return ""
    if line is None:
        return path
    suffix = f":{line}"
    if end_line and end_line != line:
        suffix += f"-{end_line}"
    if column:
        suffix += f":{column}"
    return f"{path}{suffix}"


def _non_production(path: str) -> bool:
    normalized = path.casefold().replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    filename = parts[-1] if parts else ""
    return bool(
        any(part in _NON_PRODUCTION_PARTS for part in parts)
        or filename.startswith("test_")
        or filename.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
    )


def _code_path(path: str) -> bool:
    lowered = path.casefold().split("?", 1)[0]
    return lowered.endswith(_CODE_SUFFIXES)


def _iter_strings(value: Any, *, depth: int = 0) -> Iterable[str]:
    if depth > 7:
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key) in _SKIP_RECURSIVE_KEYS:
                continue
            yield from _iter_strings(item, depth=depth + 1)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_strings(item, depth=depth + 1)
    elif isinstance(value, str):
        yield value


def _iter_mappings(value: Any, *, depth: int = 0) -> Iterable[Mapping[str, Any]]:
    if depth > 7:
        return
    if isinstance(value, Mapping):
        yield value
        for key, item in value.items():
            if str(key) in _SKIP_RECURSIVE_KEYS:
                continue
            yield from _iter_mappings(item, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_mappings(item, depth=depth + 1)


def _rule_id(item: Mapping[str, Any]) -> str:
    return _text(
        _first(
            item,
            "rule_id",
            "rule",
            "check_id",
            "test_id",
            "code",
            "Code",
            "RuleID",
            "DetectorName",
            "id",
            "advisory_id",
        ),
        180,
    )


def _symbol(item: Mapping[str, Any]) -> str:
    return _text(_first(item, "symbol", "function", "component", "name", "method_name"), 240)


def _source_excerpt(item: Mapping[str, Any], *, secret_tool: bool) -> str:
    if secret_tool:
        return "Secret value intentionally redacted; review only the exact path, line, detector, and immutable artifact."
    value = _first(item, "source_excerpt", "code_excerpt", "snippet", "line_text", "source_line")
    if isinstance(value, (list, tuple)):
        value = "\n".join(_text(part, 300) for part in value[:12])
    return _redact(value, 1400) if value else ""


def _problem_signature(rule: str, message: str, symbol: str) -> str:
    normalized = rule.casefold().replace("-", "_")
    signatures = {
        "tls_verify_disabled": "TLS verification disabled pattern (`verify=False` or `rejectUnauthorized: false`).",
        "python_eval_exec": "Dynamic execution pattern (`eval(...)` or `exec(...)`).",
        "python_shell_true": "Subprocess invocation with `shell=True`.",
        "python_os_system": "Direct `os.system(...)` command execution.",
        "unsafe_yaml_load": "`yaml.load(...)` without verified safe-loader evidence.",
        "pickle_loads": "Unsafe deserialization pattern using `pickle.load` or `pickle.loads`.",
        "js_inner_html": "Direct `.innerHTML = ...` assignment.",
        "react_dangerous_html": "React `dangerouslySetInnerHTML` usage requiring sanitization evidence.",
        "complexity_hotspot": f"Concentrated branching in `{symbol or 'the identified function/component'}`.",
    }
    return signatures.get(normalized, _redact(message or rule or symbol, 700))


def _recommendation(rule: str, category: str, fallback: Any) -> str:
    if _text(fallback):
        return _redact(fallback, 1800)
    normalized = rule.casefold().replace("-", "_")
    if normalized == "tls_verify_disabled":
        return "Restore certificate verification, remove insecure transport exceptions, add a regression test for the verified TLS path, and rerun the exact-SHA security checks."
    if normalized in {"python_eval_exec", "python_shell_true", "python_os_system"}:
        return "Replace the unsafe execution boundary with a bounded argument-based implementation, add characterization and abuse-case tests, then rerun static analysis on the exact remediation commit."
    if normalized in {"js_inner_html", "react_dangerous_html"}:
        return "Use framework-safe rendering or an approved sanitizer, add an XSS regression test, and rerun the exact-SHA frontend security checks."
    if "complex" in normalized or category == "architecture":
        return "Decompose the hotspot into bounded functions or components, preserve behavior with characterization tests, and enforce the approved complexity threshold in CI."
    if category == "dependency":
        return "Confirm the affected package and installed version, apply the smallest supported upgrade or constraint, regenerate the lockfile when applicable, and rerun all dependency analyzers."
    if category == "secret":
        return "Verify whether the candidate is a real credential without exposing it, revoke and rotate confirmed secrets, remove them from reachable history, and rerun both history-aware scanners."
    return "Review the exact source anchor, apply the smallest bounded correction, run targeted and full regression tests, and rerun NICO against the remediation commit."


def _verification(item: Mapping[str, Any], category: str, path: str, line: int | None) -> list[str]:
    output: list[str] = []
    raw = item.get("acceptance_criteria") or item.get("verification") or item.get("verification_test") or []
    values = [raw] if isinstance(raw, str) else list(raw) if isinstance(raw, (list, tuple)) else []
    seen: set[str] = set()
    for value in values:
        text = _redact(value, 1200)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    if not output:
        anchor = _location_text(path, line)
        output.append(f"The exact-SHA rerun no longer reports this condition at {anchor}." if anchor else "The exact-SHA rerun records the finding as resolved or explicitly accepted with rationale and expiry.")
        if category in {"static", "security", "secret", "architecture"}:
            output.append("Targeted tests and the repository's full required-check suite pass on the remediation commit.")
    return output[:6]


def _priority(value: Any, *, severity: str = "", verified_material: bool = False) -> str:
    text = _text(value).upper()
    if text in {"P0", "P1", "P2", "P3"}:
        return text
    lowered = severity.casefold()
    if verified_material and lowered in {"critical", "high", "error"}:
        return "P1"
    return "P2"


def _stable_id(*values: Any) -> str:
    digest = hashlib.sha256("|".join(_text(value).casefold() for value in values).encode("utf-8")).hexdigest()[:12].upper()
    return f"NICO-CODE-{digest}"


def _canonical_record(item: Mapping[str, Any], commit_sha: str) -> dict[str, Any]:
    path, line, column, end_line = _finding_location(item)
    rule = _rule_id(item) or _text(item.get("finding_family"), 180)
    title = _text(_first(item, "decision_title", "title", "interpretation"), 500) or rule or "Technical finding requires disposition"
    category = _text(item.get("category") or "technical").casefold().replace(" ", "_")
    symbol = _symbol(item)
    evidence = _redact(_first(item, "fact", "evidence", "observed_fact", "message"), 1800)
    verified_material = item.get("material") is True or _text(item.get("disposition")).casefold() == "verified_material"
    identifier = _text(_first(item, "finding_id", "id"), 180) or _stable_id(category, path, line, rule, title)
    return {
        "finding_id": identifier,
        "priority": _priority(item.get("priority") or item.get("severity"), severity=_text(item.get("severity")), verified_material=verified_material),
        "category": category,
        "status": _text(item.get("status") or item.get("disposition") or "review_required"),
        "title": title,
        "path": path,
        "line": line,
        "column": column,
        "end_line": end_line,
        "location": _location_text(path, line, column, end_line),
        "symbol": symbol,
        "rule_id": rule,
        "evidence_source": _text(_first(item, "scanner", "scanner_name", "tool", "evidence_source")) or "canonical finding",
        "exact_commit_sha": commit_sha,
        "exact_commit_match": item.get("exact_commit_match") is not False,
        "artifact_hash": _text(item.get("artifact_hash"), 160),
        "observed_evidence": evidence or "The canonical finding was retained against the assessed immutable commit.",
        "problematic_code": _problem_signature(rule, evidence, symbol),
        "source_excerpt": _source_excerpt(item, secret_tool=category == "secret"),
        "interpretation": _redact(item.get("interpretation") or title, 1200),
        "business_impact": _redact(item.get("business_impact") or item.get("impact"), 1600) or "Requires human technical disposition before the condition can be treated as resolved.",
        "recommended_correction": _recommendation(rule, category, item.get("recommendation")),
        "verification": _verification(item, category, path, line),
        "rollback": _redact(item.get("rollback"), 1200) or "Revert the isolated remediation change if targeted or full verification fails; retain the failed evidence and keep client delivery blocked.",
        "exit_criteria": _verification(item, category, path, line),
        "owner_role": _text(item.get("owner_role") or "Product Engineering"),
        "effort": _text(item.get("effort") or "Requires estimation"),
        "evidence_quality": _text(item.get("evidence_quality") or ("verified material" if verified_material else "review required")),
        "confidence": _text(item.get("confidence") or "bounded"),
        "human_disposition_required": True,
        "production_scope": item.get("production_scope") is not False and not _non_production(path),
        "record_source": "canonical_finding",
    }


def _scanner_records(canonical: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    for candidate in (canonical.get("scanner_execution_records"), assessment.get("scanner_execution_records")):
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, Mapping)]
    return []


def _scanner_finding_record(scanner: Mapping[str, Any], finding: Mapping[str, Any], commit_sha: str) -> dict[str, Any]:
    tool = _scanner_name(_first(scanner, "scanner_name", "tool", "scanner"))
    path, line, column, end_line = _finding_location(finding)
    rule = _rule_id(finding)
    category = _text(scanner.get("category") or finding.get("category") or "technical").casefold()
    secret_tool = tool in _SECRET_TOOLS or category == "secret"
    severity = _text(_first(finding, "severity", "level", "issue_severity", "confidence"))
    message = _redact(_first(finding, "message", "description", "Description", "title", "summary"), 1500)
    if secret_tool:
        message = "Potential secret candidate requires human disposition; the secret value is intentionally redacted."
    title = _text(_first(finding, "title", "description", "Description"), 400) or rule or f"{tool} finding requires disposition"
    if secret_tool:
        title = f"{tool} secret candidate requires disposition"
    identifier = _stable_id(tool, rule, path, line, title)
    verified = scanner.get("verified") is True and scanner.get("exact_commit_match") is True
    return {
        "finding_id": identifier,
        "priority": _priority(None, severity=severity, verified_material=finding.get("material") is True),
        "category": category,
        "status": "review_required",
        "title": title,
        "path": path,
        "line": line,
        "column": column,
        "end_line": end_line,
        "location": _location_text(path, line, column, end_line),
        "symbol": _symbol(finding),
        "rule_id": rule,
        "evidence_source": tool,
        "exact_commit_sha": commit_sha,
        "exact_commit_match": scanner.get("exact_commit_match") is True,
        "artifact_hash": _text(scanner.get("artifact_hash"), 160),
        "observed_evidence": message or f"{tool} retained a candidate at the exact source anchor.",
        "problematic_code": _problem_signature(rule, message, _symbol(finding)),
        "source_excerpt": _source_excerpt(finding, secret_tool=secret_tool),
        "interpretation": "This is a scanner candidate, not a confirmed production defect, until the exact source context and applicability are reviewed.",
        "business_impact": "A confirmed instance could affect security, correctness, maintainability, or delivery reliability; an unconfirmed candidate affects evidence assurance only.",
        "recommended_correction": _recommendation(rule, category, None),
        "verification": _verification(finding, category, path, line),
        "rollback": "Revert the isolated remediation change if targeted or full verification fails; retain the failed evidence and keep client delivery blocked.",
        "exit_criteria": _verification(finding, category, path, line),
        "owner_role": "Senior Product Engineer" if category != "architecture" else "Product Engineering Architect",
        "effort": "Requires source review",
        "evidence_quality": "verified exact-SHA artifact" if verified else "review-limited exact-SHA candidate",
        "confidence": severity or "unknown",
        "human_disposition_required": True,
        "production_scope": not _non_production(path),
        "record_source": "scanner_finding",
    }


def _complexity_records(canonical: Mapping[str, Any], commit_sha: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for item in _iter_mappings(canonical):
        complexity = item.get("cyclomatic_complexity")
        if not isinstance(complexity, (int, float)) or isinstance(complexity, bool) or complexity < 30:
            continue
        path, line, column, end_line = _finding_location(item)
        if not path or line is None or not _code_path(path) or _non_production(path):
            continue
        symbol = _symbol(item)
        key = (path.casefold(), line, symbol.casefold())
        if key in seen:
            continue
        seen.add(key)
        loc = item.get("loc")
        grade = _text(item.get("grade"))
        method = _text(item.get("method"))
        evidence = f"cyclomatic_complexity={int(complexity)}"
        if isinstance(loc, (int, float)):
            evidence += f"; loc={int(loc)}"
        if grade:
            evidence += f"; grade={grade}"
        if method:
            evidence += f"; method={method}"
        base = {
            "finding_family": "complexity_hotspot",
            "priority": "P1",
            "category": "architecture",
            "status": "open",
            "title": f"Reduce complexity in {symbol or PurePosixPath(path).name}",
            "location": _location_text(path, line, column, end_line),
            "path": path,
            "line": line,
            "column": column,
            "end_line": end_line,
            "symbol": symbol,
            "fact": evidence,
            "interpretation": "High-complexity code hotspot",
            "business_impact": "Concentrated branch logic increases regression risk, review cost, and the difficulty of safe change.",
            "recommendation": "Decompose the hotspot into bounded modules, add characterization tests, and enforce complexity and change-size thresholds in CI.",
            "owner_role": "Product Engineering Architect",
            "effort": "M-L",
            "source_excerpt": item.get("source_excerpt") or item.get("code_excerpt"),
            "exact_commit_match": True,
        }
        output.append(_canonical_record(base, commit_sha))
    return output


def _risk_string_records(canonical: Mapping[str, Any], commit_sha: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in _iter_strings(canonical):
        for match in _RISK_LINE.finditer(raw):
            path = match.group("path").replace("\\", "/")
            if _non_production(path):
                continue
            line = int(match.group("line"))
            column = int(match.group("column")) if match.group("column") else None
            rule = match.group("rule")
            message = match.group("message")
            base = {
                "priority": "P1" if rule.casefold() == "tls_verify_disabled" else "P2",
                "category": "security",
                "status": "review_required",
                "title": message,
                "location": _location_text(path, line, column),
                "path": path,
                "line": line,
                "column": column,
                "rule_id": rule,
                "fact": f"risk_pattern={rule}; exact immutable commit={commit_sha}",
                "interpretation": message,
                "business_impact": "Unsafe code patterns can create security or reliability defects and require exact-source human review.",
                "recommendation": _recommendation(rule, "security", None),
                "owner_role": "Senior Product Engineer",
                "effort": "S-M",
                "exact_commit_match": True,
            }
            output.append(_canonical_record(base, commit_sha))
        for match in _HOTSPOT_LINE.finditer(raw):
            path = match.group("path").replace("\\", "/")
            if _non_production(path):
                continue
            line = int(match.group("line"))
            symbol = _text(match.group("symbol"))
            complexity = int(match.group("complexity"))
            base = {
                "priority": "P1",
                "category": "architecture",
                "status": "open",
                "title": f"Reduce complexity in {symbol or PurePosixPath(path).name}",
                "location": _location_text(path, line),
                "path": path,
                "line": line,
                "symbol": symbol,
                "finding_family": "complexity_hotspot",
                "fact": f"cyclomatic_complexity={complexity}; source=retained exact-SHA architecture evidence",
                "interpretation": "High-complexity code hotspot",
                "business_impact": "Concentrated branch logic increases regression risk, review cost, and the difficulty of safe change.",
                "recommendation": "Decompose the hotspot into bounded modules, add characterization tests, and enforce complexity and change-size thresholds in CI.",
                "owner_role": "Product Engineering Architect",
                "effort": "M-L",
                "exact_commit_match": True,
            }
            output.append(_canonical_record(base, commit_sha))
    return output


def _semantic_key(item: Mapping[str, Any]) -> tuple[str, str, int, str, str]:
    return (
        _text(item.get("category")).casefold(),
        _text(item.get("path")).casefold(),
        int(item.get("line") or 0),
        _text(item.get("rule_id") or item.get("symbol")).casefold(),
        _text(item.get("title")).casefold(),
    )


def _quality(item: Mapping[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(item.get("record_source") == "canonical_finding"),
        int(bool(item.get("location"))),
        int(bool(item.get("observed_evidence"))),
        int(bool(item.get("recommended_correction"))),
    )


def _merge_records(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str, int, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, int, str, str]] = []
    for raw in records:
        item = deepcopy(dict(raw))
        key = _semantic_key(item)
        if key not in selected:
            selected[key] = item
            order.append(key)
            continue
        preferred, other = (item, selected[key]) if _quality(item) > _quality(selected[key]) else (selected[key], item)
        merged = deepcopy(preferred)
        for field, value in other.items():
            if merged.get(field) in (None, "", [], {}):
                merged[field] = deepcopy(value)
        selected[key] = merged
    return [selected[key] for key in order]


def build_finding_remediation_register(canonical: Mapping[str, Any]) -> dict[str, Any]:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    commit_sha = _text(identity.get("commit_sha") or canonical.get("commit_sha"))
    canonical_findings = [item for item in canonical.get("canonical_findings") or [] if isinstance(item, Mapping)]
    records: list[dict[str, Any]] = [_canonical_record(item, commit_sha) for item in canonical_findings]

    for scanner in _scanner_records(canonical):
        if scanner.get("applicable") is False:
            continue
        for finding in scanner.get("findings") or []:
            if isinstance(finding, Mapping):
                records.append(_scanner_finding_record(scanner, finding, commit_sha))

    records.extend(_complexity_records(canonical, commit_sha))
    records.extend(_risk_string_records(canonical, commit_sha))
    deduplicated = _merge_records(records)

    excluded_non_production = [item for item in deduplicated if item.get("production_scope") is False]
    client_records = [item for item in deduplicated if item.get("production_scope") is not False]
    code_findings = [item for item in client_records if _code_path(_text(item.get("path"))) and isinstance(item.get("line"), int)]
    operational_findings = [item for item in client_records if item not in code_findings]

    code_findings.sort(key=lambda item: (item.get("priority") not in {"P0", "P1"}, _text(item.get("path")), int(item.get("line") or 0), _text(item.get("finding_id"))))
    operational_findings.sort(key=lambda item: (item.get("priority") not in {"P0", "P1"}, _text(item.get("title"))))
    return {
        "version": VERSION,
        "exact_commit_sha": commit_sha,
        "code_findings": code_findings,
        "operational_findings": operational_findings,
        "excluded_non_production_findings": excluded_non_production,
        "summary": {
            "canonical_finding_count": len(canonical_findings),
            "deduplicated_record_count": len(deduplicated),
            "exact_source_code_finding_count": len(code_findings),
            "operational_or_context_finding_count": len(operational_findings),
            "excluded_non_production_count": len(excluded_non_production),
            "raw_secret_values_retained": False,
            "human_disposition_required": True,
            "client_delivery_allowed": False,
        },
    }


def _bullet_values(values: Any) -> list[str]:
    if isinstance(values, str):
        return [_redact(values, 1200)] if _text(values) else []
    if isinstance(values, (list, tuple)):
        return [_redact(value, 1200) for value in values if _text(value)]
    return []


def finding_register_markdown(register: Mapping[str, Any], *, spanish: bool) -> str:
    code_findings = [item for item in register.get("code_findings") or [] if isinstance(item, Mapping)]
    operational = [item for item in register.get("operational_findings") or [] if isinstance(item, Mapping)]
    heading = "## Registro de hallazgos y remediación" if spanish else "## Finding and Remediation Register"
    lines = [
        heading,
        "",
        (
            "Este registro usa únicamente evidencia vinculada al commit exacto. Los candidatos no verificados se etiquetan para revisión; no se convierten en defectos confirmados."
            if spanish
            else "This register uses evidence bound to the exact assessed commit. Unverified candidates remain labeled for review and are not converted into confirmed defects."
        ),
        "",
        f"- Exact commit: `{_text(register.get('exact_commit_sha'))}`",
        f"- Exact-source code findings: {len(code_findings)}",
        f"- Operational/context findings: {len(operational)}",
        "- Secret values retained: no",
        "",
    ]
    for item in code_findings:
        lines.extend(
            [
                f"### {_text(item.get('priority'))} · {_text(item.get('title'))} · {_text(item.get('finding_id'))}",
                "",
                f"- Exact source: `{_text(item.get('location'))}`",
                f"- Function / component: `{_text(item.get('symbol')) or 'not retained'}`",
                f"- Analyzer / rule: `{_text(item.get('evidence_source'))}` · `{_text(item.get('rule_id')) or 'not retained'}`",
                f"- Evidence quality: {_text(item.get('evidence_quality'))}; exact commit match={bool(item.get('exact_commit_match'))}",
                f"- Problematic code or signature: {_text(item.get('problematic_code')) or 'Open the exact source anchor for review.'}",
            ]
        )
        if _text(item.get("source_excerpt")):
            lines.append(f"- Bounded source excerpt: `{_redact(item.get('source_excerpt'), 1400)}`")
        else:
            lines.append("- Bounded source excerpt: not retained; open the exact immutable source location before editing.")
        lines.extend(
            [
                f"- Observed evidence: {_text(item.get('observed_evidence'))}",
                f"- Interpretation: {_text(item.get('interpretation'))}",
                f"- Business consequence: {_text(item.get('business_impact'))}",
                f"- Specific correction: {_text(item.get('recommended_correction'))}",
                f"- Owner / effort: {_text(item.get('owner_role'))} · {_text(item.get('effort'))}",
                "- Verification:",
            ]
        )
        lines.extend(f"  - {value}" for value in _bullet_values(item.get("verification")))
        lines.extend(
            [
                f"- Rollback: {_text(item.get('rollback'))}",
                "- Exit criteria:",
            ]
        )
        lines.extend(f"  - {value}" for value in _bullet_values(item.get("exit_criteria")))
        lines.append("")

    if operational:
        lines.extend(["## Operational and Context Findings", ""])
        for item in operational:
            lines.extend(
                [
                    f"### {_text(item.get('priority'))} · {_text(item.get('title'))} · {_text(item.get('finding_id'))}",
                    "",
                    "- Source classification: operational, dependency, or context evidence; no single code line is claimed.",
                    f"- Evidence: {_text(item.get('observed_evidence'))}",
                    f"- Business consequence: {_text(item.get('business_impact'))}",
                    f"- Recommended action: {_text(item.get('recommended_correction'))}",
                    "",
                ]
            )
    return "\n".join(lines).strip() + "\n"


def render_finding_register_pdf(register: Mapping[str, Any], *, spanish: bool) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    code_findings = [item for item in register.get("code_findings") or [] if isinstance(item, Mapping)]
    operational = [item for item in register.get("operational_findings") or [] if isinstance(item, Mapping)]
    rendered = code_findings[:MAX_PDF_CODE_FINDINGS]
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    heading = ParagraphStyle("RegisterHeading", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=colors.HexColor("#075985"), spaceAfter=10)
    subheading = ParagraphStyle("RegisterSubheading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=colors.HexColor("#075985"), spaceAfter=7)
    body = ParagraphStyle("RegisterBody", parent=styles["BodyText"], fontSize=8, leading=10.6, textColor=colors.HexColor("#334155"), spaceAfter=4)
    label = ParagraphStyle("RegisterLabel", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#0f172a"))
    warning = ParagraphStyle("RegisterWarning", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#92400e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=.8, borderPadding=7, spaceAfter=10)

    def paragraph(value: Any, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(html.escape(_redact(value, 5000)).replace("\n", "<br/>") or "Not retained", style)

    story: list[Any] = [
        Spacer(1, .18 * inch),
        paragraph("Registro de hallazgos y remediación" if spanish else "Finding and Remediation Register", heading),
        paragraph(
            "Cada registro separa el hecho observado, la interpretación y la corrección propuesta. Los candidatos no verificados requieren revisión humana."
            if spanish
            else "Each record separates observed evidence, interpretation, and proposed correction. Unverified candidates require human review and are not presented as confirmed defects.",
            body,
        ),
        paragraph(f"Exact commit: {_text(register.get('exact_commit_sha'))}", label),
        paragraph(f"Exact-source findings: {len(code_findings)} · Operational/context findings: {len(operational)}", body),
    ]
    if len(code_findings) > len(rendered):
        story.append(paragraph(f"The PDF renders {len(rendered)} highest-priority exact-source findings; {len(code_findings) - len(rendered)} additional structured records remain in JSON.", warning))
    story.append(PageBreak())

    for index, item in enumerate(rendered, 1):
        title = f"{_text(item.get('priority'))} · {_text(item.get('title'))} · {_text(item.get('finding_id'))}"
        story.append(paragraph(title, subheading))
        verification = "<br/>".join(f"• {html.escape(value)}" for value in _bullet_values(item.get("verification"))) or "Requires exact-SHA rerun"
        exit_criteria = "<br/>".join(f"• {html.escape(value)}" for value in _bullet_values(item.get("exit_criteria"))) or "Requires human disposition"
        excerpt = _text(item.get("source_excerpt")) or "Not retained; open the exact immutable source location before editing."
        rows = [
            [paragraph("Exact source", label), paragraph(item.get("location"))],
            [paragraph("Function / component", label), paragraph(item.get("symbol") or "Not retained")],
            [paragraph("Analyzer / rule", label), paragraph(f"{_text(item.get('evidence_source'))} · {_text(item.get('rule_id')) or 'not retained'}")],
            [paragraph("Evidence quality", label), paragraph(f"{_text(item.get('evidence_quality'))}; exact commit match={bool(item.get('exact_commit_match'))}")],
            [paragraph("Problematic code", label), paragraph(item.get("problematic_code"))],
            [paragraph("Bounded source excerpt", label), paragraph(excerpt)],
            [paragraph("Observed evidence", label), paragraph(item.get("observed_evidence"))],
            [paragraph("Technical consequence", label), paragraph(item.get("interpretation"))],
            [paragraph("Business consequence", label), paragraph(item.get("business_impact"))],
            [paragraph("Specific correction", label), paragraph(item.get("recommended_correction"))],
            [paragraph("Verification", label), Paragraph(verification, body)],
            [paragraph("Rollback", label), paragraph(item.get("rollback"))],
            [paragraph("Exit criteria", label), Paragraph(exit_criteria, body)],
            [paragraph("Owner / effort", label), paragraph(f"{_text(item.get('owner_role'))} · {_text(item.get('effort'))}")],
            [paragraph("Disposition", label), paragraph("PROPOSED · EXACT SOURCE REVIEW AND HUMAN APPROVAL REQUIRED")],
        ]
        table = Table(rows, colWidths=[1.45 * inch, 5.35 * inch], repeatRows=0)
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(table)
        story.append(Spacer(1, .12 * inch))
        story.append(paragraph("Implementation sequence", subheading))
        anchor = _text(item.get("location"))
        sequence = [
            f"1. Open {anchor} at commit {_text(register.get('exact_commit_sha'))} and retain the reviewed source context.",
            "2. Add or confirm characterization tests before editing.",
            "3. Apply the smallest bounded correction without broadening scope.",
            "4. Run targeted tests, applicable analyzers, and the full required-check suite.",
            "5. Rerun NICO on the remediation commit and confirm the finding is resolved or explicitly dispositioned.",
        ]
        story.extend(paragraph(value, body) for value in sequence)
        if index < len(rendered) or operational:
            story.append(PageBreak())

    if operational:
        story.append(paragraph("Operational and Context Findings", heading))
        story.append(paragraph("These records do not claim a single source-code location. They remain decision-relevant and require the stated operational or dependency disposition.", body))
        for item in operational[:25]:
            story.append(paragraph(f"{_text(item.get('priority'))} · {_text(item.get('title'))} · {_text(item.get('finding_id'))}", subheading))
            story.append(paragraph(f"Evidence: {_text(item.get('observed_evidence'))}", body))
            story.append(paragraph(f"Action: {_text(item.get('recommended_correction'))}", body))

    document = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=.55 * inch, rightMargin=.55 * inch, topMargin=.55 * inch, bottomMargin=.6 * inch, invariant=1, title="NICO Finding and Remediation Register", author="NICO")
    document.build(story)
    return buffer.getvalue()


__all__ = [
    "VERSION",
    "build_finding_remediation_register",
    "finding_register_markdown",
    "render_finding_register_pdf",
]
