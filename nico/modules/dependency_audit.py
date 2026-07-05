    # Static risky version check (fallback)
    static_high = 0
    for dep_file in dep_files:
        try:
            content = Path(dep_file).read_text(encoding="utf-8", errors="ignore")
            for risky, reason in KNOWN_RISKY.items():
                if risky in content:
                    result["risky_dependencies"].append({
                        "file": dep_file,
                        "dependency": risky,
                        "reason": reason,
                        "severity": "high",
                    })
                    static_high += 1
        except Exception:
            continue

    # Real vulnerability scanning
    pip_vulns = _run_pip_audit(path)
    npm_vulns = _run_npm_audit(path)

    all_vulns = pip_vulns + npm_vulns
    result["risky_dependencies"].extend(all_vulns)
    result["vulnerabilities_found"] = len(all_vulns) + static_high

    for v in all_vulns:
        sev = v.get("severity", "")
        if sev == "critical":
            result["critical_count"] += 1
        elif sev == "high":
            result["high_count"] += 1

    result["high_count"] += static_high