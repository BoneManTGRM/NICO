from __future__ import annotations

import hashlib
import math
import re
import time
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

import nico.full_assessment_complexity_evidence as complexity_engine
import nico.full_assessment_scorecard as scorecard
import nico.hosted_assessment as hosted
import nico.mid_assessment_handlers as mid_handlers
import nico.scanner_worker as scanner_worker
import nico.snapshot_assessment_handlers as snapshot_handlers
import nico.snapshot_repository_evidence as snapshot_repository


INTEGRITY_VERSION = "nico-assessment-score-integrity-v1"
MAX_BUILTIN_FILES = 4_000
MAX_BUILTIN_FILE_BYTES = 1_000_000
MAX_BUILTIN_TOTAL_BYTES = 40_000_000
SKIP_PARTS = {
    ".git",
    "node_modules",
    ".next",
    "dist",
    "build",
    "coverage",
    ".venv",
    "venv",
    "__pycache__",
    "vendor",
}
TEXT_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".txt", ".md", ".sh", ".html", ".css", ".xml", ".env",
}
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}
LOW_CONFIDENCE_PATH_PARTS = {
    "test", "tests", "fixture", "fixtures", "example", "examples", "sample", "samples",
    "docs", "documentation", "template", "templates",
}
PLACEHOLDER_TERMS = {
    "example", "sample", "placeholder", "changeme", "change_me", "dummy", "fake", "test",
    "testing", "redacted", "replace_me", "replace-me", "your_key", "your-key", "your_token",
    "your-token", "none", "null", "undefined", "not-a-secret", "notasecret",
}

SPECIFIC_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
)
GENERIC_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?P<label>api[_-]?key|secret|token|password|passwd|client[_-]?secret)\b"
    r"\s*[:=]\s*['\"]?(?P<value>[A-Za-z0-9_./+=:@-]{8,})"
)
RISK_PATTERNS = tuple(hosted.RISK_PATTERNS)

_ORIGINAL_HOSTED_SCAN_FILES = hosted.scan_files
_ORIGINAL_HOSTED_ANALYZE_SECRETS = hosted.analyze_secrets
_ORIGINAL_RUN_TOOL = scanner_worker.run_tool
_ORIGINAL_ATTACHMENT_HANDLER = snapshot_handlers._snapshot_evidence_attachment_handler
_ORIGINAL_ANALYZE_JS = complexity_engine._analyze_javascript
_ORIGINAL_COLLECT_COMPLEXITY = complexity_engine.collect_complexity_evidence


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}…{value[-4:]}"


def _path_is_low_confidence(path: str) -> bool:
    parts = {part.lower() for part in Path(path).parts}
    name = Path(path).name.lower()
    return bool(parts & LOW_CONFIDENCE_PATH_PARTS) or name.startswith(("readme", ".env.example")) or name.endswith((".example", ".sample"))


def _line_is_pattern_definition(line: str) -> bool:
    lowered = line.lower()
    return any(
        marker in lowered
        for marker in (
            "re.compile(", "secret_patterns", "generic_secret_assignment", "github_token", "aws_access_key",
            "private_key", "detect-secrets", "gitleaks", "trufflehog",
        )
    )


def _looks_placeholder(value: str) -> bool:
    lowered = value.lower().strip("'\" ")
    if lowered.startswith(("${", "env.", "process.env", "os.getenv", "secret:", "secrets.")):
        return True
    return any(term in lowered for term in PLACEHOLDER_TERMS)


def _confidence_for(path: str, line: str, kind: str, value: str) -> tuple[str, str]:
    low_context = _path_is_low_confidence(path) or _line_is_pattern_definition(line) or _looks_placeholder(value)
    if kind in {"private_key", "github_token", "aws_access_key"}:
        if low_context:
            return "medium", "Specific credential shape appears in an example, test, documentation, placeholder, or detector-definition context."
        return "high", "Specific credential shape appears in non-example repository content."

    diversity = sum(bool(re.search(pattern, value)) for pattern in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    entropy = _entropy(value)
    if low_context:
        return "low", "Generic secret assignment appears in an example, test, documentation, placeholder, or detector-definition context."
    if len(value) >= 24 and diversity >= 3 and entropy >= 3.4:
        return "medium", "Generic secret assignment contains a non-placeholder, token-like value that requires human validation."
    return "low", "Generic assignment lacks enough entropy or diversity for a material credential claim."


def classify_secret_candidates(path: str, text: str) -> list[dict[str, Any]]:
    """Return masked, confidence-classified candidates without retaining raw values."""

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[int, str, str]] = set()
    for line_no, line in enumerate(str(text or "").splitlines(), 1):
        for kind, pattern in SPECIFIC_SECRET_PATTERNS:
            for match in pattern.finditer(line):
                value = match.group(0)
                confidence, reason = _confidence_for(path, line, kind, value)
                key = (line_no, kind, hashlib.sha256(value.encode()).hexdigest()[:16])
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(
                    {
                        "path": path,
                        "line": line_no,
                        "kind": kind,
                        "confidence": confidence,
                        "masked_preview": _mask(value),
                        "fingerprint": key[2],
                        "reason": reason,
                    }
                )
        for match in GENERIC_SECRET_ASSIGNMENT.finditer(line):
            value = match.group("value")
            kind = str(match.group("label") or "generic_secret").lower().replace("-", "_")
            confidence, reason = _confidence_for(path, line, kind, value)
            key = (line_no, kind, hashlib.sha256(value.encode()).hexdigest()[:16])
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "path": path,
                    "line": line_no,
                    "kind": kind,
                    "confidence": confidence,
                    "masked_preview": _mask(value),
                    "fingerprint": key[2],
                    "reason": reason,
                }
            )
    return candidates


def _candidate_summary(candidate: dict[str, Any]) -> str:
    return (
        f"{candidate.get('path')}:{candidate.get('line')}: potential {candidate.get('kind')} "
        f"({candidate.get('confidence')} confidence, fingerprint={candidate.get('fingerprint')}, "
        f"masked={candidate.get('masked_preview')}) — {candidate.get('reason')}"
    )


def calibrated_scan_files(files: dict[str, str]) -> dict[str, Any]:
    result = dict(_ORIGINAL_HOSTED_SCAN_FILES(files))
    candidates = [candidate for path, text in files.items() for candidate in classify_secret_candidates(path, text)]
    high = [item for item in candidates if item["confidence"] == "high"]
    medium = [item for item in candidates if item["confidence"] == "medium"]
    low = [item for item in candidates if item["confidence"] == "low"]
    material = high + medium
    result["secrets"] = [_candidate_summary(item) for item in material]
    result["secret_candidates"] = candidates[:100]
    result["high_confidence_secret_hits"] = len(high)
    result["medium_confidence_secret_hits"] = len(medium)
    result["low_confidence_secret_hits"] = len(low)
    result["potential_secret_pattern_hits"] = len(material)
    result["secret_classifier_version"] = INTEGRITY_VERSION
    result["secret_classifier_rule"] = "Low-confidence examples, placeholders, tests, documentation, and detector definitions are disclosed but do not count as material credential hits."
    return result


def calibrated_analyze_secrets(file_scan: dict[str, Any]) -> dict[str, Any]:
    high = _int(file_scan.get("high_confidence_secret_hits"))
    medium = _int(file_scan.get("medium_confidence_secret_hits"))
    low = _int(file_scan.get("low_confidence_secret_hits"))
    evidence = [
        f"Classified sampled-file credential candidates: high={high}, medium={medium}, low={low}.",
        "Raw credential values are never printed or retained in the hosted report.",
    ]
    evidence.extend(str(item) for item in _list(file_scan.get("secrets"))[:15])
    findings: list[str] = []
    if high:
        findings.append(f"Immediately triage {high} high-confidence credential candidate(s) and rotate any confirmed credential outside NICO.")
    if medium:
        findings.append(f"Human-validate {medium} medium-confidence credential candidate(s) before client delivery.")
    score = max(25, min(88, 84 - high * 35 - medium * 10 - min(4, low)))
    unavailable = [
        "Sampled current-tree review is not full git-history proof; a dedicated history scanner remains required for a high-confidence clean claim.",
    ]
    return {
        "score": score,
        "summary": "Secrets review uses masked, confidence-classified current-tree candidates and does not treat examples or detector definitions as confirmed credentials.",
        "evidence": evidence + findings,
        "findings": findings,
        "unavailable": unavailable,
    }


def _eligible_file(path: Path, root: Path, *, source_only: bool = False) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if any(part in SKIP_PARTS for part in relative.parts):
        return False
    if not path.is_file() or path.is_symlink():
        return False
    suffix = path.suffix.lower()
    if source_only:
        return suffix in SOURCE_SUFFIXES
    return suffix in TEXT_SUFFIXES or path.name in {"Dockerfile", "Procfile", ".env", ".env.example"}


def _bounded_files(root: Path, *, source_only: bool = False) -> tuple[list[Path], list[str]]:
    selected: list[Path] = []
    notes: list[str] = []
    total = 0
    for path in root.rglob("*"):
        if len(selected) >= MAX_BUILTIN_FILES:
            notes.append(f"Built-in scan stopped after {MAX_BUILTIN_FILES} eligible files.")
            break
        if not _eligible_file(path, root, source_only=source_only):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > MAX_BUILTIN_FILE_BYTES:
            continue
        if total + size > MAX_BUILTIN_TOTAL_BYTES:
            notes.append(f"Built-in scan stopped after {MAX_BUILTIN_TOTAL_BYTES} readable bytes.")
            break
        total += size
        selected.append(path)
    return selected, notes


def _read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:4096]:
        return None
    return data.decode("utf-8", errors="replace")


def _built_in_secret_scan(repo_path: Path) -> dict[str, Any]:
    started = time.monotonic()
    paths, notes = _bounded_files(repo_path)
    candidates: list[dict[str, Any]] = []
    for path in paths:
        text = _read_text(path)
        if text is None:
            continue
        candidates.extend(classify_secret_candidates(path.relative_to(repo_path).as_posix(), text))
    high = [item for item in candidates if item["confidence"] == "high"]
    medium = [item for item in candidates if item["confidence"] == "medium"]
    low = [item for item in candidates if item["confidence"] == "low"]
    status = "failed" if high else "passed"
    summary = (
        f"NICO current-tree credential classifier inspected {len(paths)} file(s): "
        f"high={len(high)}, medium={len(medium)}, low={len(low)}."
    )
    preview = "\n".join(_candidate_summary(item) for item in (high + medium + low)[:30])
    return {
        "scanner": "nico-secrets",
        "command_intent": "Masked current-tree credential review",
        "status": status,
        "exit_code": 1 if high else 0,
        "duration_seconds": round(time.monotonic() - started, 2),
        "evidence_summary": summary,
        "safe_output_preview": preview,
        "risk_severity": "high" if high else "medium" if medium else "low",
        "recommended_repair": "Triage high and medium candidates; rotate only confirmed credentials outside NICO.",
        "unavailable_data_notes": notes + ["This built-in scanner covers the checked-out current tree, not complete git history."],
        "secret_redaction_applied": bool(candidates),
        "finding_counts": {"high": len(high), "medium": len(medium), "low": len(low)},
        "files_scanned": len(paths),
        "classifier_version": INTEGRITY_VERSION,
        "full_history_covered": False,
    }


def _built_in_static_scan(repo_path: Path) -> dict[str, Any]:
    started = time.monotonic()
    paths, notes = _bounded_files(repo_path, source_only=True)
    findings: list[str] = []
    by_rule: Counter[str] = Counter()
    for path in paths:
        text = _read_text(path)
        if text is None:
            continue
        relative = path.relative_to(repo_path).as_posix()
        for line_no, line in enumerate(text.splitlines(), 1):
            for name, pattern, message in RISK_PATTERNS:
                if pattern.search(line):
                    by_rule[name] += 1
                    if len(findings) < 100:
                        findings.append(f"{relative}:{line_no}: {name} — {message}")
    status = "failed" if findings else "passed"
    summary = f"NICO current-tree static risk scanner inspected {len(paths)} source file(s) and returned {sum(by_rule.values())} material pattern hit(s)."
    return {
        "scanner": "nico-static",
        "command_intent": "Bounded current-tree static risk review",
        "status": status,
        "exit_code": 1 if findings else 0,
        "duration_seconds": round(time.monotonic() - started, 2),
        "evidence_summary": summary,
        "safe_output_preview": "\n".join(findings[:30]),
        "risk_severity": "high" if findings else "low",
        "recommended_repair": "Review each material rule hit and confirm exploitability before repair prioritization.",
        "unavailable_data_notes": notes + ["Built-in pattern coverage does not replace language-specific semantic analyzers."],
        "secret_redaction_applied": False,
        "finding_count": sum(by_rule.values()),
        "findings_by_rule": dict(sorted(by_rule.items())),
        "files_scanned": len(paths),
        "analyzer_version": INTEGRITY_VERSION,
    }


def calibrated_run_tool(name: str, cfg: dict[str, Any], repo_path: Path, env: dict[str, str], deadline: float) -> dict[str, Any]:
    if name == "nico-secrets":
        return _built_in_secret_scan(repo_path)
    if name == "nico-static":
        return _built_in_static_scan(repo_path)
    return _ORIGINAL_RUN_TOOL(name, cfg, repo_path, env, deadline)


def _scanner_result(scanner: dict[str, Any], name: str) -> dict[str, Any]:
    for item in _list(scanner.get("scanner_results")):
        if isinstance(item, dict) and str(item.get("scanner") or "").lower() == name:
            return item
    return {}


def calibrated_secrets_section(repo: dict[str, Any], scanner: dict[str, Any]) -> dict[str, Any]:
    signals = _dict(repo.get("code_signal_evidence"))
    sampled_material = _int(signals.get("potential_secret_pattern_hits"))
    built_in = _scanner_result(scanner, "nico-secrets")
    counts = _dict(built_in.get("finding_counts"))
    high, medium, low = _int(counts.get("high")), _int(counts.get("medium")), _int(counts.get("low"))
    built_in_ran = str(built_in.get("status") or "") in {"passed", "failed"}

    score = 68
    if built_in_ran:
        score += 12
    score -= min(55, high * 35)
    score -= min(18, medium * 8)
    score -= min(4, low)
    if sampled_material and not (high or medium):
        score -= min(8, sampled_material * 4)
    if not built_in_ran:
        score = min(score, 68)
    if high:
        score = min(score, 44)
    score = max(20, min(88, score))

    evidence = [
        f"Sampled repository text returned {sampled_material} material potential secret-pattern hit(s) after confidence classification.",
        f"NICO current-tree credential scanner status={built_in.get('status') or 'not run'}; high={high}, medium={medium}, low={low}; files={_int(built_in.get('files_scanned'))}.",
        "Candidate output is masked and fingerprinted; raw credential values are not retained in assessment evidence.",
    ]
    findings: list[str] = []
    if high:
        findings.append(f"Immediately triage {high} high-confidence credential candidate(s) and rotate confirmed credentials outside NICO.")
    if medium:
        findings.append(f"Human-validate {medium} medium-confidence credential candidate(s) before report approval.")
    unavailable = [
        "Full git-history secret coverage is not verified; current-tree classification cannot prove that repository history contains no credentials.",
        "Live gitleaks/trufflehog history evidence was not attached to this score unless separately recorded by the scanner worker.",
    ]
    confidence = "current-tree-scanner-bound" if built_in_ran else "limited"
    return scorecard._section(
        "secrets_review",
        "Secrets Exposure Review",
        score,
        "Secrets maturity reflects confidence-classified sampled evidence plus a masked full-checkout current-tree scanner; history coverage remains a separate limitation.",
        evidence,
        findings=findings,
        unavailable=unavailable,
        confidence=confidence,
    )


def calibrated_static_section(repo: dict[str, Any], scanner: dict[str, Any]) -> dict[str, Any]:
    signals = _dict(repo.get("code_signal_evidence"))
    sampled = _int(signals.get("risk_pattern_hits"))
    built_in = _scanner_result(scanner, "nico-static")
    built_hits = _int(built_in.get("finding_count"))
    built_in_ran = str(built_in.get("status") or "") in {"passed", "failed"}
    external = scorecard._tool_group(scanner, {"bandit", "semgrep", "eslint"})

    score = 54
    score += 16 if built_in_ran else 0
    score += min(18, len(external["run"]) * 6)
    score -= min(30, max(sampled, built_hits) * 5)
    score -= len(external["failed"]) * 8
    score -= len(external["timed_out"]) * 6
    if not built_in_ran:
        score = min(score, 60)
    score = max(25, min(90, score))

    evidence = [
        f"Sampled-file static risk-pattern hits: {sampled}.",
        f"NICO current-tree static scanner status={built_in.get('status') or 'not run'}; material hits={built_hits}; files={_int(built_in.get('files_scanned'))}.",
        f"Language-specific analyzers run: {', '.join(sorted(external['run'])) or 'none'}; failed={len(external['failed'])}; timed out={len(external['timed_out'])}; unavailable={len(external['unavailable'])}.",
    ]
    findings: list[str] = []
    material = max(sampled, built_hits)
    if material:
        findings.append(f"Review {material} current-tree static risk-pattern hit(s) before report approval.")
    if external["failed"] or external["timed_out"]:
        findings.append("One or more language-specific analyzers failed or timed out; semantic static-analysis evidence is incomplete.")
    unavailable = [
        "The built-in scanner is bounded pattern analysis, not proof that no vulnerability exists.",
    ]
    if not external["run"]:
        unavailable.append("Bandit, Semgrep, and ESLint semantic artifacts were not attached; the current-tree built-in result remains review-limited.")
    return scorecard._section(
        "static_analysis",
        "Static Analysis",
        score,
        "Static-analysis maturity combines a bounded full-checkout current-tree scanner with available language-specific analyzers and material finding counts.",
        evidence,
        findings=findings,
        unavailable=unavailable,
        confidence="current-tree-scanner-bound" if built_in_ran else "limited",
    )


def _mask_js_comments_and_strings(text: str) -> str:
    chars = list(text)
    index = 0
    state = "code"
    quote = ""
    while index < len(chars):
        current = chars[index]
        nxt = chars[index + 1] if index + 1 < len(chars) else ""
        if state == "code":
            if current == "/" and nxt == "/":
                chars[index] = chars[index + 1] = " "
                index += 2
                state = "line_comment"
                continue
            if current == "/" and nxt == "*":
                chars[index] = chars[index + 1] = " "
                index += 2
                state = "block_comment"
                continue
            if current in {"'", '"', "`"}:
                quote = current
                chars[index] = " "
                index += 1
                state = "string"
                continue
        elif state == "line_comment":
            if current == "\n":
                state = "code"
            else:
                chars[index] = " "
        elif state == "block_comment":
            if current == "*" and nxt == "/":
                chars[index] = chars[index + 1] = " "
                index += 2
                state = "code"
                continue
            if current != "\n":
                chars[index] = " "
        elif state == "string":
            if current == "\\":
                chars[index] = " "
                if index + 1 < len(chars) and chars[index + 1] != "\n":
                    chars[index + 1] = " "
                index += 2
                continue
            if current == quote:
                chars[index] = " "
                state = "code"
            elif current != "\n":
                chars[index] = " "
        index += 1
    return "".join(chars)


def _match_brace(text: str, opening: int) -> int | None:
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _branch_count(text: str) -> int:
    patterns = (
        r"\bif\s*\(", r"\bfor\s*\(", r"\bwhile\s*\(", r"\bcase\b", r"\bcatch\s*\(",
        r"\?\?", r"&&", r"\|\|", r"\?(?![?.])",
    )
    return sum(len(re.findall(pattern, text)) for pattern in patterns)


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def _js_function_spans(masked: str) -> list[dict[str, Any]]:
    patterns: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("function", re.compile(r"\b(?:async\s+)?function\s+(?P<name>[A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{")),
        ("arrow", re.compile(r"\b(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*\{")),
        ("method", re.compile(r"(?m)^[ \t]*(?:public\s+|private\s+|protected\s+|static\s+|async\s+|get\s+|set\s+)*(?P<name>[A-Za-z_$][\w$]*)\s*\([^;{}\n]*\)\s*(?::\s*[^={\n]+)?\s*\{")),
    )
    reserved = {"if", "for", "while", "switch", "catch", "with", "function", "constructor"}
    spans: list[dict[str, Any]] = []
    seen_openings: set[int] = set()
    for method, pattern in patterns:
        for match in pattern.finditer(masked):
            name = str(match.groupdict().get("name") or "<anonymous>")
            if method == "method" and name in reserved:
                continue
            opening = masked.find("{", match.start(), match.end())
            if opening < 0 or opening in seen_openings:
                continue
            closing = _match_brace(masked, opening)
            if closing is None:
                continue
            seen_openings.add(opening)
            spans.append({"name": name, "start": match.start(), "opening": opening, "end": closing + 1, "method": method})

    concise_arrow = re.compile(
        r"\b(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?"
        r"(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*(?!\{)(?P<body>[^;\n]+)"
    )
    for match in concise_arrow.finditer(masked):
        spans.append({"name": match.group("name"), "start": match.start(), "opening": match.start("body"), "end": match.end("body"), "method": "concise_arrow"})

    spans.sort(key=lambda item: (int(item["start"]), -int(item["end"])))
    unique: list[dict[str, Any]] = []
    keys: set[tuple[int, int, str]] = set()
    for item in spans:
        key = (int(item["start"]), int(item["end"]), str(item["name"]))
        if key not in keys:
            keys.add(key)
            unique.append(item)
    return unique


def _without_nested(text: str, item: dict[str, Any], spans: list[dict[str, Any]]) -> str:
    start, end = int(item["opening"]), int(item["end"])
    body = list(text[start:end])
    for nested in spans:
        nested_start, nested_end = int(nested["start"]), int(nested["end"])
        if nested is item or nested_start <= start or nested_end > end:
            continue
        left, right = nested_start - start, nested_end - start
        for index in range(max(0, left), min(len(body), right)):
            if body[index] != "\n":
                body[index] = " "
    return "".join(body)


def analyze_javascript_functions(path: str, text: str) -> dict[str, Any]:
    masked = _mask_js_comments_and_strings(text)
    spans = _js_function_spans(masked)
    functions: list[dict[str, Any]] = []
    for item in spans:
        body = _without_nested(masked, item, spans)
        complexity = max(1, 1 + _branch_count(body))
        start_line = _line_number(masked, int(item["start"]))
        end_line = _line_number(masked, int(item["end"]))
        functions.append(
            {
                "path": path,
                "name": str(item["name"]),
                "line": start_line,
                "end_line": end_line,
                "loc": max(1, end_line - start_line + 1),
                "cyclomatic_complexity": complexity,
                "grade": complexity_engine._grade(complexity),
                "max_nesting": complexity_engine._brace_nesting(body),
                "language": "javascript-typescript",
                "method": "function_level_lexical_v2",
            }
        )

    module_chars = list(masked)
    for item in spans:
        for index in range(int(item["start"]), min(len(module_chars), int(item["end"]))):
            if module_chars[index] != "\n":
                module_chars[index] = " "
    module_text = "".join(module_chars)
    module_branches = _branch_count(module_text)
    if module_branches:
        module_loc = sum(1 for line in module_text.splitlines() if line.strip())
        complexity = 1 + module_branches
        functions.append(
            {
                "path": path,
                "name": "<module-logic>",
                "line": 1,
                "end_line": max(1, len(text.splitlines())),
                "loc": max(1, module_loc),
                "cyclomatic_complexity": complexity,
                "grade": complexity_engine._grade(complexity),
                "max_nesting": complexity_engine._brace_nesting(module_text),
                "language": "javascript-typescript",
                "method": "module_residual_lexical_v2",
            }
        )

    imports, internal_imports = complexity_engine._js_imports(text)
    source_loc = sum(1 for line in masked.splitlines() if line.strip())
    return {
        "status": "analyzed",
        "path": path,
        "language": "javascript-typescript",
        "source_loc": source_loc,
        "functions": functions,
        "declared_function_count": len([item for item in functions if item["name"] != "<module-logic>"]),
        "module_logic_units": len([item for item in functions if item["name"] == "<module-logic>"]),
        "imports": sorted(imports),
        "internal_imports": sorted(internal_imports),
        "fan_out": len(imports),
        "internal_fan_out": len(internal_imports),
        "method": "function_level_lexical_v2",
    }


def calibrated_collect_complexity_evidence(files: dict[str, str]) -> dict[str, Any]:
    result = dict(_ORIGINAL_COLLECT_COMPLEXITY(files))
    result["analyzer_version"] = "nico-bounded-complexity-v2"
    result["javascript_typescript_method"] = "function_level_lexical_v2"
    result["javascript_typescript_function_units"] = sum(
        int(item.get("declared_function_count") or 0)
        for path, text in files.items()
        if complexity_engine._is_source_path(path) and path.lower().endswith((".js", ".jsx", ".ts", ".tsx"))
        for item in [analyze_javascript_functions(path, text)]
    )
    notes = [str(note) for note in _list(result.get("unavailable_data_notes")) if "module-level values" not in str(note)]
    if _int(result.get("javascript_typescript_files_analyzed")):
        notes.append(
            "JavaScript and TypeScript complexity uses bounded function-level lexical extraction rather than a full language parser; dynamic syntax and parser-level semantics remain lower-confidence than Python AST metrics."
        )
    result["unavailable_data_notes"] = list(dict.fromkeys(notes))
    result["scope"] = "Authorized GitHub text-file sample with Python AST and bounded JavaScript/TypeScript function-level extraction; tests, build, distribution, dependency, and minified paths are excluded."
    return result


def calibrated_attachment_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    result = _ORIGINAL_ATTACHMENT_HANDLER(context, outputs)
    if result.get("status") != "complete":
        return result
    scanner_step = _dict(outputs.get("scanner_worker"))
    scan = _dict(scanner_step.get("scan"))
    sanitized = []
    for item in _list(scan.get("scanner_results")):
        if not isinstance(item, dict):
            continue
        sanitized.append(
            {
                key: item.get(key)
                for key in (
                    "scanner", "command_intent", "status", "exit_code", "duration_seconds", "evidence_summary",
                    "risk_severity", "recommended_repair", "unavailable_data_notes", "finding_counts",
                    "finding_count", "findings_by_rule", "files_scanned", "classifier_version",
                    "analyzer_version", "full_history_covered", "secret_redaction_applied",
                )
                if key in item
            }
        )
    evidence = _dict(result.get("scanner_evidence"))
    evidence["scanner_results"] = sanitized
    evidence["score_integrity_version"] = INTEGRITY_VERSION
    result["scanner_evidence"] = evidence
    result["evidence"] = evidence
    return result


def _rebind() -> None:
    hosted.scan_files = calibrated_scan_files
    hosted.analyze_secrets = calibrated_analyze_secrets
    snapshot_repository.scan_files = calibrated_scan_files

    complexity_engine._analyze_javascript = analyze_javascript_functions
    complexity_engine.collect_complexity_evidence = calibrated_collect_complexity_evidence
    snapshot_repository.collect_complexity_evidence = calibrated_collect_complexity_evidence

    scorecard._secrets_section = calibrated_secrets_section
    scorecard._static_section = calibrated_static_section

    scanner_worker.TOOL_CATALOG = {
        "nico-secrets": {
            "binary": "nico-internal",
            "intent": "Masked current-tree credential review",
            "tier": "built_in",
        },
        "nico-static": {
            "binary": "nico-internal",
            "intent": "Bounded current-tree static risk review",
            "tier": "built_in",
        },
        **{key: value for key, value in scanner_worker.TOOL_CATALOG.items() if key not in {"nico-secrets", "nico-static"}},
    }
    scanner_worker.run_tool = calibrated_run_tool

    snapshot_handlers._snapshot_evidence_attachment_handler = calibrated_attachment_handler
    mid_handlers._snapshot_evidence_attachment_handler = calibrated_attachment_handler


def install_assessment_score_integrity() -> dict[str, Any]:
    installed = bool(getattr(scanner_worker, "_nico_score_integrity_installed", False))
    _rebind()
    scanner_worker._nico_score_integrity_installed = True
    return {
        "status": "already_installed" if installed else "installed",
        "version": INTEGRITY_VERSION,
        "built_in_scanners": ["nico-secrets", "nico-static"],
        "secret_rule": "Only high- and medium-confidence sampled candidates count as material secret-pattern hits; all output is masked.",
        "complexity_rule": "JavaScript and TypeScript are measured with bounded function-level units rather than one whole-file synthetic unit.",
        "score_rule": "Scores change only from improved evidence quality and completed scanner coverage; section weights and strict trust caps are unchanged.",
    }


__all__ = [
    "INTEGRITY_VERSION",
    "analyze_javascript_functions",
    "calibrated_analyze_secrets",
    "calibrated_collect_complexity_evidence",
    "calibrated_run_tool",
    "calibrated_scan_files",
    "classify_secret_candidates",
    "install_assessment_score_integrity",
]
