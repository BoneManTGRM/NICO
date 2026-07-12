from __future__ import annotations

import hashlib
import json
import shutil
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import nico.full_assessment_scorecard as scorecard
import nico.mid_assessment_handlers as mid_handlers
import nico.scanner_runtime_compat as runtime_compat
import nico.scanner_worker as scanner_worker
import nico.snapshot_assessment_handlers as snapshot_handlers

DEPENDENCY_TRIAGE_VERSION = "nico-dependency-scanner-triage-v1"
_DEPENDENCY_TOOLS = {"pip-audit", "npm-audit", "osv-scanner"}
_DELEGATE_RUN_TOOL: Callable[..., dict[str, Any]] | None = None
_DEPENDENCY_SECTION_DELEGATE: Callable[..., dict[str, Any]] | None = None
_ATTACHMENT_DELEGATE: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _fingerprint(*parts: Any) -> str:
    material = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(material.encode("utf-8", errors="replace")).hexdigest()[:20]


def _normalized_name(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _json_payload(value: str) -> tuple[Any, str | None]:
    text = str(value or "").strip()
    if not text:
        return None, "Scanner completed without machine-readable JSON output."
    try:
        return json.loads(text), None
    except json.JSONDecodeError:
        starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
        if starts:
            try:
                return json.loads(text[min(starts) :]), None
            except json.JSONDecodeError:
                pass
    return None, "Scanner output could not be parsed as JSON."


def _safe_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(value)
        for key, value in record.items()
        if key
        in {
            "fingerprint",
            "ecosystem",
            "package",
            "installed_version",
            "advisory_ids",
            "fixed_versions",
            "max_severity",
            "source_path",
            "material",
            "review_required",
            "disposition_reason",
        }
    }


def parse_pip_audit(payload: Any) -> dict[str, Any]:
    root = _dict(payload)
    dependencies = _list(root.get("dependencies")) if root else _list(payload)
    resolved_versions: dict[str, str] = {}
    vulnerabilities: list[dict[str, Any]] = []
    for dependency in dependencies:
        item = _dict(dependency)
        name = _normalized_name(item.get("name"))
        version = str(item.get("version") or "").strip()
        if name:
            resolved_versions[name] = version
        for vulnerability in _list(item.get("vulns") or item.get("vulnerabilities")):
            finding = _dict(vulnerability)
            advisory_id = str(finding.get("id") or "unknown")
            aliases = sorted({str(alias) for alias in _list(finding.get("aliases")) if str(alias)})
            fix_versions = sorted({str(value) for value in _list(finding.get("fix_versions")) if str(value)})
            vulnerabilities.append(
                {
                    "fingerprint": _fingerprint("pypi", name, version, advisory_id),
                    "ecosystem": "PyPI",
                    "package": name,
                    "installed_version": version,
                    "advisory_ids": sorted({advisory_id, *aliases}),
                    "fixed_versions": fix_versions,
                    "material": True,
                    "review_required": False,
                    "disposition_reason": "pip-audit reported this advisory for the resolved dependency version.",
                }
            )
    return {
        "resolved_versions": dict(sorted(resolved_versions.items())),
        "vulnerabilities": sorted(vulnerabilities, key=lambda item: (item["package"], item["installed_version"], item["advisory_ids"])),
    }


def parse_npm_audit(payload: Any) -> dict[str, Any]:
    root = _dict(payload)
    vulnerabilities: list[dict[str, Any]] = []
    for package, raw in _dict(root.get("vulnerabilities")).items():
        item = _dict(raw)
        advisory_ids: set[str] = set()
        for via in _list(item.get("via")):
            if isinstance(via, dict):
                for key in ("source", "url", "name", "title"):
                    value = str(via.get(key) or "").strip()
                    if value:
                        advisory_ids.add(value)
            elif str(via).strip():
                advisory_ids.add(str(via).strip())
        vulnerabilities.append(
            {
                "fingerprint": _fingerprint("npm", package, item.get("range"), item.get("severity")),
                "ecosystem": "npm",
                "package": _normalized_name(package),
                "installed_version": str(item.get("range") or "unknown"),
                "advisory_ids": sorted(advisory_ids),
                "fixed_versions": [],
                "max_severity": str(item.get("severity") or "unknown"),
                "material": True,
                "review_required": False,
                "disposition_reason": "npm audit reported this package in the current lockfile dependency graph.",
            }
        )
    metadata = _dict(root.get("metadata"))
    counts = _dict(metadata.get("vulnerabilities"))
    return {
        "resolved_versions": {},
        "vulnerabilities": sorted(vulnerabilities, key=lambda item: (item["package"], item["max_severity"])),
        "severity_counts": {str(key): _int(value) for key, value in counts.items()},
    }


def _fixed_versions(vulnerabilities: list[dict[str, Any]], identifiers: set[str]) -> list[str]:
    versions: set[str] = set()
    for vulnerability in vulnerabilities:
        item = _dict(vulnerability)
        ids = {str(item.get("id") or ""), *{str(value) for value in _list(item.get("aliases"))}}
        if identifiers and not (identifiers & ids):
            continue
        for affected in _list(item.get("affected")):
            for range_item in _list(_dict(affected).get("ranges")):
                for event in _list(_dict(range_item).get("events")):
                    fixed = str(_dict(event).get("fixed") or "").strip()
                    if fixed:
                        versions.add(fixed)
    return sorted(versions)


def parse_osv(payload: Any) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for result in _list(_dict(payload).get("results")):
        source = _dict(_dict(result).get("source"))
        source_path = str(source.get("path") or "")
        for package_entry in _list(_dict(result).get("packages")):
            package_record = _dict(package_entry)
            package = _dict(package_record.get("package"))
            name = _normalized_name(package.get("name"))
            version = str(package.get("version") or "unknown")
            ecosystem = str(package.get("ecosystem") or "unknown")
            vulnerabilities = [_dict(value) for value in _list(package_record.get("vulnerabilities"))]
            groups = _list(package_record.get("groups"))
            if not groups:
                groups = [
                    {
                        "ids": [str(item.get("id") or "unknown")],
                        "aliases": _list(item.get("aliases")),
                        "max_severity": "",
                    }
                    for item in vulnerabilities
                ]
            for group in groups:
                item = _dict(group)
                identifiers = {
                    str(value)
                    for value in [*_list(item.get("ids")), *_list(item.get("aliases"))]
                    if str(value)
                }
                canonical = sorted(identifiers) or ["unknown"]
                fingerprint = _fingerprint(ecosystem, name, version, *canonical)
                records[fingerprint] = {
                    "fingerprint": fingerprint,
                    "ecosystem": ecosystem,
                    "package": name,
                    "installed_version": version,
                    "advisory_ids": canonical,
                    "fixed_versions": _fixed_versions(vulnerabilities, identifiers),
                    "max_severity": str(item.get("max_severity") or "unknown"),
                    "source_path": source_path,
                    "material": False,
                    "review_required": True,
                    "disposition_reason": "OSV source resolution requires corroboration by the ecosystem-specific resolved dependency graph.",
                }
    return sorted(records.values(), key=lambda item: (item["ecosystem"], item["package"], item["installed_version"], item["advisory_ids"]))


def _completed_result(
    name: str,
    cfg: dict[str, Any],
    *,
    returncode: int,
    duration: float,
    records: list[dict[str, Any]],
    resolved_versions: dict[str, str] | None = None,
    severity_counts: dict[str, int] | None = None,
    stderr: str = "",
) -> dict[str, Any]:
    preview, redacted = scanner_worker.redact(stderr)
    count = len(records)
    return {
        "scanner": name,
        "command_intent": cfg.get("intent", name),
        "status": "passed",
        "execution_status": "completed_with_findings" if count else "completed_clean",
        "execution_completed": True,
        "exit_code": returncode,
        "duration_seconds": duration,
        "evidence_summary": f"{name} structured dependency scan completed: vulnerability records={count}.",
        "safe_output_preview": f"vulnerability_records={count}",
        "risk_severity": "high" if count else "low",
        "recommended_repair": "Update affected resolved dependencies and rerun all dependency scanners." if count else "Retain lockfiles and rerun after dependency changes.",
        "unavailable_data_notes": [preview[:1000]] if preview else [],
        "secret_redaction_applied": redacted,
        "finding_count": count,
        "material_finding_count": count,
        "review_finding_count": 0,
        "dependency_records": [_safe_record(item) for item in records[:200]],
        "resolved_versions": dict(sorted((resolved_versions or {}).items())),
        "severity_counts": severity_counts or {},
        "triage_version": DEPENDENCY_TRIAGE_VERSION,
    }


def _run_pip_audit(cfg: dict[str, Any], repo_path: Path, env: dict[str, str], deadline: float) -> dict[str, Any]:
    if not scanner_worker.ENABLE_SCANNER_EXECUTION:
        return scanner_worker.unavailable_result("pip-audit", cfg, ["Scanner execution disabled by NICO_ENABLE_SCANNER_EXECUTION."])
    if shutil.which("pip-audit") is None:
        return scanner_worker.unavailable_result("pip-audit", cfg, ["pip-audit is not installed in this worker image."])
    requirements = repo_path / "requirements.txt"
    if not requirements.exists():
        return scanner_worker.unavailable_result("pip-audit", cfg, ["requirements.txt not found."])
    timeout = max(1, min(runtime_compat.OSV_TIMEOUT_SECONDS, int(deadline - time.monotonic())))
    try:
        returncode, stdout, stderr, duration, timed_out = runtime_compat._communicate(
            ["pip-audit", "-r", str(requirements), "-f", "json"], cwd=repo_path, env=env, timeout=timeout
        )
    except Exception as exc:
        return scanner_worker.unavailable_result("pip-audit", cfg, [f"{type(exc).__name__}: {exc}"])
    if timed_out:
        result = scanner_worker.unavailable_result("pip-audit", cfg, [f"pip-audit timed out after {timeout} seconds."])
        result.update({"status": "timeout", "execution_status": "timeout", "execution_completed": False, "duration_seconds": duration})
        return result
    payload, parse_error = _json_payload(stdout)
    parsed = parse_pip_audit(payload) if parse_error is None else {"resolved_versions": {}, "vulnerabilities": []}
    normal_exit = returncode in {0, 1}
    if not normal_exit or parse_error:
        result = scanner_worker.unavailable_result("pip-audit", cfg, [parse_error or stderr or f"exit={returncode}"])
        result.update({"status": "failed", "execution_status": "execution_failed", "execution_completed": False, "exit_code": returncode, "duration_seconds": duration})
        return result
    return _completed_result(
        "pip-audit",
        cfg,
        returncode=int(returncode or 0),
        duration=duration,
        records=parsed["vulnerabilities"],
        resolved_versions=parsed["resolved_versions"],
        stderr=stderr,
    )


def _run_npm_audit(cfg: dict[str, Any], repo_path: Path, env: dict[str, str], deadline: float) -> dict[str, Any]:
    if not scanner_worker.ENABLE_SCANNER_EXECUTION:
        return scanner_worker.unavailable_result("npm-audit", cfg, ["Scanner execution disabled by NICO_ENABLE_SCANNER_EXECUTION."])
    if shutil.which("npm") is None:
        return scanner_worker.unavailable_result("npm-audit", cfg, ["npm is not installed in this worker image."])
    lockfiles = sorted(repo_path.rglob("package-lock.json"), key=lambda path: (len(path.parts), str(path)))
    if not lockfiles:
        return scanner_worker.unavailable_result("npm-audit", cfg, ["package-lock.json not found."])
    timeout = max(1, min(runtime_compat.OSV_TIMEOUT_SECONDS, int(deadline - time.monotonic())))
    cwd = lockfiles[0].parent
    try:
        returncode, stdout, stderr, duration, timed_out = runtime_compat._communicate(
            ["npm", "audit", "--json", "--package-lock-only", "--ignore-scripts"], cwd=cwd, env=env, timeout=timeout
        )
    except Exception as exc:
        return scanner_worker.unavailable_result("npm-audit", cfg, [f"{type(exc).__name__}: {exc}"])
    if timed_out:
        result = scanner_worker.unavailable_result("npm-audit", cfg, [f"npm audit timed out after {timeout} seconds."])
        result.update({"status": "timeout", "execution_status": "timeout", "execution_completed": False, "duration_seconds": duration})
        return result
    payload, parse_error = _json_payload(stdout)
    parsed = parse_npm_audit(payload) if parse_error is None else {"resolved_versions": {}, "vulnerabilities": [], "severity_counts": {}}
    normal_exit = returncode in {0, 1}
    if not normal_exit or parse_error:
        result = scanner_worker.unavailable_result("npm-audit", cfg, [parse_error or stderr or f"exit={returncode}"])
        result.update({"status": "failed", "execution_status": "execution_failed", "execution_completed": False, "exit_code": returncode, "duration_seconds": duration})
        return result
    return _completed_result(
        "npm-audit",
        cfg,
        returncode=int(returncode or 0),
        duration=duration,
        records=parsed["vulnerabilities"],
        severity_counts=parsed.get("severity_counts"),
        stderr=stderr,
    )


def _run_osv(cfg: dict[str, Any], repo_path: Path, env: dict[str, str], deadline: float) -> dict[str, Any]:
    result = deepcopy(runtime_compat._run_osv(cfg, repo_path, env, deadline))
    if result.get("execution_completed") is not True:
        return result
    records: list[dict[str, Any]] = []
    for variant, command in runtime_compat._osv_commands(repo_path):
        timeout = max(1, min(runtime_compat.OSV_TIMEOUT_SECONDS, int(deadline - time.monotonic())))
        try:
            returncode, stdout, _stderr, _duration, timed_out = runtime_compat._communicate(command, cwd=repo_path, env=env, timeout=timeout)
        except Exception:
            break
        if timed_out:
            break
        payload, parse_error = _json_payload(stdout)
        if returncode in {0, 1} and parse_error is None:
            records = parse_osv(payload)
            result["command_variant"] = variant
            break
        if not runtime_compat._cli_mismatch(_stderr):
            break
    result["finding_count"] = len(records)
    result["material_finding_count"] = 0
    result["review_finding_count"] = len(records)
    result["dependency_records"] = [_safe_record(item) for item in records[:200]]
    result["triage_version"] = DEPENDENCY_TRIAGE_VERSION
    result["evidence_summary"] = f"OSV-Scanner source-resolution scan completed: grouped advisory records={len(records)}; ecosystem corroboration pending."
    return result


def dependency_run_tool(name: str, cfg: dict[str, Any], repo_path: Path, env: dict[str, str], deadline: float) -> dict[str, Any]:
    if name == "pip-audit":
        return _run_pip_audit(cfg, repo_path, env, deadline)
    if name == "npm-audit":
        return _run_npm_audit(cfg, repo_path, env, deadline)
    if name == "osv-scanner":
        return _run_osv(cfg, repo_path, env, deadline)
    if _DELEGATE_RUN_TOOL is None:
        raise RuntimeError("Dependency scanner triage was not installed before worker execution.")
    return _DELEGATE_RUN_TOOL(name, cfg, repo_path, env, deadline)


def _scanner_result(scanner: dict[str, Any], name: str) -> dict[str, Any]:
    for item in _list(scanner.get("scanner_results")):
        if isinstance(item, dict) and str(item.get("scanner") or "").lower() == name:
            return item
    return {}


def _id_set(record: dict[str, Any]) -> set[str]:
    return {str(value) for value in _list(record.get("advisory_ids")) if str(value)}


def corroborate_dependency_records(scanner: dict[str, Any]) -> dict[str, Any]:
    pip_result = _scanner_result(scanner, "pip-audit")
    npm_result = _scanner_result(scanner, "npm-audit")
    osv_result = _scanner_result(scanner, "osv-scanner")
    pip_completed = pip_result.get("execution_completed") is True
    npm_completed = npm_result.get("execution_completed") is True
    pip_versions = {_normalized_name(key): str(value) for key, value in _dict(pip_result.get("resolved_versions")).items()}
    pip_vulns = [_dict(item) for item in _list(pip_result.get("dependency_records"))]
    npm_vulns = [_dict(item) for item in _list(npm_result.get("dependency_records"))]
    material = [*_list(pip_vulns), *_list(npm_vulns)]
    review: list[dict[str, Any]] = []
    for raw in _list(osv_result.get("dependency_records")):
        record = deepcopy(_dict(raw))
        ecosystem = str(record.get("ecosystem") or "").lower()
        name = _normalized_name(record.get("package"))
        scanned_version = str(record.get("installed_version") or "")
        if ecosystem == "pypi" and pip_completed:
            resolved = pip_versions.get(name)
            matching = [
                item
                for item in pip_vulns
                if _normalized_name(item.get("package")) == name and (_id_set(item) & _id_set(record))
            ]
            if matching:
                record["material"] = True
                record["review_required"] = False
                record["disposition_reason"] = "Corroborated by pip-audit for the resolved Python dependency graph."
                material.append(record)
            else:
                record["material"] = False
                record["review_required"] = True
                record["disposition_reason"] = (
                    f"OSV resolved {name}={scanned_version}, while pip-audit resolved {resolved or 'not present'} with no matching advisory."
                )
                review.append(record)
        elif ecosystem == "npm" and npm_completed:
            matching = [item for item in npm_vulns if _normalized_name(item.get("package")) == name]
            if matching:
                record["material"] = True
                record["review_required"] = False
                record["disposition_reason"] = "Corroborated by npm audit for the current lockfile graph."
                material.append(record)
            else:
                record["material"] = False
                record["review_required"] = True
                record["disposition_reason"] = "OSV source-resolution record was not corroborated by npm audit for the current lockfile graph."
                review.append(record)
        else:
            record["material"] = False
            record["review_required"] = True
            record["disposition_reason"] = "Ecosystem-specific audit evidence was not completed; OSV record remains review-required."
            review.append(record)
    unique_material = {str(item.get("fingerprint") or _fingerprint(item)): _safe_record(item) for item in material}
    unique_review = {str(item.get("fingerprint") or _fingerprint(item)): _safe_record(item) for item in review}
    return {
        "material_records": list(unique_material.values()),
        "review_records": list(unique_review.values()),
        "pip_audit_completed": pip_completed,
        "npm_audit_completed": npm_completed,
        "osv_completed": osv_result.get("execution_completed") is True,
    }


def dependency_section_with_corroboration(repo: dict[str, Any], scanner: dict[str, Any]) -> dict[str, Any]:
    if _DEPENDENCY_SECTION_DELEGATE is None:
        raise RuntimeError("Dependency score delegate is unavailable.")
    section = deepcopy(_DEPENDENCY_SECTION_DELEGATE(repo, scanner))
    triage = corroborate_dependency_records(scanner)
    material = _list(triage.get("material_records"))
    review = _list(triage.get("review_records"))
    completed_count = sum(bool(triage.get(key)) for key in ("pip_audit_completed", "npm_audit_completed", "osv_completed"))
    evidence = [str(item) for item in _list(section.get("evidence"))]
    evidence.append(
        f"Corroborated dependency triage: material={len(material)}, review-required={len(review)}, structured scanners completed={completed_count}/3."
    )
    findings = [str(item) for item in _list(section.get("findings"))]
    unavailable = [str(item) for item in _list(section.get("unavailable"))]
    if material:
        findings.append(f"Remediate {len(material)} corroborated dependency vulnerability record(s) before approval.")
        section["score"] = min(_int(section.get("score")), 55)
    elif completed_count >= 2:
        section["score"] = max(_int(section.get("score")), 82)
    if review:
        findings.append(f"Human-review {len(review)} uncorroborated OSV source-resolution record(s); they are not scored as confirmed installed vulnerabilities.")
    if completed_count < 2:
        unavailable.append("Fewer than two structured dependency scanners completed; cross-scanner corroboration remains incomplete.")
        section["score"] = min(_int(section.get("score")), 72)
    section["status"] = "green" if section["score"] >= 80 else "yellow" if section["score"] >= 55 else "red"
    section["evidence"] = list(dict.fromkeys(evidence))
    section["verified_claims"] = section["evidence"]
    section["findings"] = list(dict.fromkeys(findings))
    section["unavailable"] = list(dict.fromkeys(unavailable))
    section["unverified_claims"] = section["unavailable"]
    section["dependency_scanner_triage"] = {
        "version": DEPENDENCY_TRIAGE_VERSION,
        "material_finding_count": len(material),
        "review_finding_count": len(review),
        "structured_scanners_completed": completed_count,
        "pip_audit_completed": bool(triage.get("pip_audit_completed")),
        "npm_audit_completed": bool(triage.get("npm_audit_completed")),
        "osv_completed": bool(triage.get("osv_completed")),
    }
    return section


SAFE_ATTACHMENT_FIELDS = (
    "execution_status",
    "execution_completed",
    "finding_count",
    "material_finding_count",
    "review_finding_count",
    "resolved_versions",
    "severity_counts",
    "triage_version",
)


def dependency_attachment_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    if _ATTACHMENT_DELEGATE is None:
        raise RuntimeError("Dependency evidence attachment bridge is unavailable.")
    result = _ATTACHMENT_DELEGATE(context, outputs)
    if not isinstance(result, dict) or result.get("status") != "complete":
        return result
    scanner_step = _dict(outputs.get("scanner_worker"))
    scan = _dict(scanner_step.get("scan"))
    raw = {
        str(item.get("scanner") or "").lower(): item
        for item in _list(scan.get("scanner_results"))
        if isinstance(item, dict) and str(item.get("scanner") or "").lower() in _DEPENDENCY_TOOLS
    }
    evidence = deepcopy(_dict(result.get("scanner_evidence") or result.get("evidence")))
    sanitized = [item for item in _list(evidence.get("scanner_results")) if isinstance(item, dict)]
    by_name = {str(item.get("scanner") or "").lower(): item for item in sanitized}
    for name, raw_item in raw.items():
        target = by_name.setdefault(name, {"scanner": name, "status": raw_item.get("status") or "unknown"})
        for field in SAFE_ATTACHMENT_FIELDS:
            if field in raw_item:
                target[field] = deepcopy(raw_item[field])
        target["dependency_records"] = [_safe_record(item) for item in _list(raw_item.get("dependency_records"))[:200]]
    evidence["scanner_results"] = list(by_name.values())
    evidence["dependency_triage_version"] = DEPENDENCY_TRIAGE_VERSION
    output = dict(result)
    output["scanner_evidence"] = evidence
    output["evidence"] = evidence
    return output


def install_dependency_scanner_triage() -> dict[str, Any]:
    global _DELEGATE_RUN_TOOL, _DEPENDENCY_SECTION_DELEGATE, _ATTACHMENT_DELEGATE
    installed = bool(getattr(scanner_worker, "_nico_dependency_scanner_triage_installed", False))
    if not installed:
        _DELEGATE_RUN_TOOL = scanner_worker.run_tool
        _DEPENDENCY_SECTION_DELEGATE = scorecard._dependency_section
        _ATTACHMENT_DELEGATE = snapshot_handlers._snapshot_evidence_attachment_handler
    scanner_worker.run_tool = dependency_run_tool
    scorecard._dependency_section = dependency_section_with_corroboration
    snapshot_handlers._snapshot_evidence_attachment_handler = dependency_attachment_handler
    mid_handlers._snapshot_evidence_attachment_handler = dependency_attachment_handler
    scanner_worker._nico_dependency_scanner_triage_installed = True
    return {
        "status": "already_installed" if installed else "installed",
        "version": DEPENDENCY_TRIAGE_VERSION,
        "tools": sorted(_DEPENDENCY_TOOLS),
        "rule": "OSV source-resolution records remain review evidence unless corroborated by the ecosystem-specific resolved dependency graph; completed pip-audit and npm audit records remain material.",
    }


__all__ = [
    "DEPENDENCY_TRIAGE_VERSION",
    "corroborate_dependency_records",
    "dependency_section_with_corroboration",
    "install_dependency_scanner_triage",
    "parse_npm_audit",
    "parse_osv",
    "parse_pip_audit",
]
