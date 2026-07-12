from __future__ import annotations

from pathlib import Path


path = Path("nico/dependency_scanner_triage.py")
text = path.read_text(encoding="utf-8")
old = '''def _run_osv(cfg: dict[str, Any], repo_path: Path, env: dict[str, str], deadline: float) -> dict[str, Any]:
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
'''
new = '''def _run_osv(cfg: dict[str, Any], repo_path: Path, env: dict[str, str], deadline: float) -> dict[str, Any]:
    if not scanner_worker.ENABLE_SCANNER_EXECUTION:
        return scanner_worker.unavailable_result("osv-scanner", cfg, ["Scanner execution disabled by NICO_ENABLE_SCANNER_EXECUTION."])
    if shutil.which("osv-scanner") is None:
        return scanner_worker.unavailable_result("osv-scanner", cfg, ["osv-scanner is not installed in this worker image."])

    attempts: list[str] = []
    for index, (variant, command) in enumerate(runtime_compat._osv_commands(repo_path)):
        timeout = max(1, min(runtime_compat.OSV_TIMEOUT_SECONDS, int(deadline - time.monotonic())))
        try:
            returncode, stdout, stderr, duration, timed_out = runtime_compat._communicate(
                command, cwd=repo_path, env=env, timeout=timeout
            )
        except Exception as exc:
            result = scanner_worker.unavailable_result("osv-scanner", cfg, [f"{type(exc).__name__}: {exc}"])
            result.update({"status": "error", "execution_status": "execution_error", "execution_completed": False})
            return result
        if timed_out:
            result = scanner_worker.unavailable_result("osv-scanner", cfg, [f"OSV-Scanner timed out after {timeout} seconds."])
            result.update({"status": "timeout", "execution_status": "timeout", "execution_completed": False, "duration_seconds": duration, "command_variant": variant})
            return result

        payload, parse_error = _json_payload(stdout)
        normal_exit = returncode in {0, 1}
        if normal_exit and parse_error is None:
            records = parse_osv(payload)
            raw_fingerprints = runtime_compat._osv_finding_fingerprints(payload)
            if returncode not in {0, None} and not records and not raw_fingerprints:
                preview, _ = scanner_worker.redact(stderr)
                attempts.append(
                    f"{variant}: exit={returncode}; nonzero exit without a parsed vulnerability record; {preview[:400] or 'no diagnostic'}"
                )
                break
            preview, redacted = scanner_worker.redact(stderr)
            return {
                "scanner": "osv-scanner",
                "command_intent": cfg.get("intent", "OSV dependency review"),
                "status": "passed",
                "execution_status": "completed_with_findings" if records else "completed_clean",
                "execution_completed": True,
                "exit_code": returncode,
                "duration_seconds": duration,
                "evidence_summary": f"OSV-Scanner source-resolution scan completed: grouped advisory records={len(records)}; ecosystem corroboration pending.",
                "safe_output_preview": f"grouped_advisory_records={len(records)}; raw_fingerprints={len(raw_fingerprints)}; command_variant={variant}",
                "risk_severity": "review" if records else "low",
                "recommended_repair": "Corroborate OSV source-resolution records with ecosystem-specific resolved dependency audits before changing packages." if records else "Retain lockfiles and rerun after dependency changes.",
                "unavailable_data_notes": [preview[:1000]] if preview else [],
                "secret_redaction_applied": redacted,
                "finding_count": len(records),
                "vulnerability_fingerprint_count": len(raw_fingerprints),
                "material_finding_count": 0,
                "review_finding_count": len(records),
                "dependency_records": [_safe_record(item) for item in records[:200]],
                "triage_version": DEPENDENCY_TRIAGE_VERSION,
                "runtime_compat_version": runtime_compat.SCANNER_RUNTIME_COMPAT_VERSION,
                "command_variant": variant,
            }

        preview, _ = scanner_worker.redact(stderr)
        attempts.append(f"{variant}: exit={returncode}; {parse_error or preview[:400] or 'no diagnostic'}")
        if index == 0 and runtime_compat._cli_mismatch(stderr):
            continue
        break

    result = scanner_worker.unavailable_result("osv-scanner", cfg, attempts or ["OSV-Scanner did not produce valid completed dependency evidence."])
    result.update({"status": "failed", "execution_status": "execution_failed", "execution_completed": False})
    return result
'''
if old not in text:
    raise RuntimeError("Expected OSV runner block was not found")
text = text.replace(old, new, 1)
needle = '''    findings = [str(item) for item in _list(section.get("findings"))]
    unavailable = [str(item) for item in _list(section.get("unavailable"))]
    if material:
'''
replacement = '''    findings = [str(item) for item in _list(section.get("findings"))]
    unavailable = [str(item) for item in _list(section.get("unavailable"))]
    if not material:
        findings = [
            item
            for item in findings
            if not ("osv vulnerability record" in item.lower() and "before report approval" in item.lower())
        ]
    if material:
'''
if needle not in text:
    raise RuntimeError("Expected dependency finding block was not found")
text = text.replace(needle, replacement, 1)
path.write_text(text, encoding="utf-8")
Path("scripts/finalize_dependency_corroboration.py").unlink(missing_ok=True)
Path(".github/workflows/finalize-dependency-corroboration.yml").unlink(missing_ok=True)
