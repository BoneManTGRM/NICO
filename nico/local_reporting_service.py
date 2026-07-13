from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Protocol

from nico.local_runtime_config import DB_PATH, REPORT_DIR
from nico.local_store import LocalStore


class LocalReportStore(Protocol):
    def payloads(self, table: str) -> list[dict[str, Any]]: ...

    def latest_scan(self) -> dict[str, Any]: ...

    def policy(self) -> dict[str, Any]: ...

    def rows(self, table: str) -> list[dict[str, Any]]: ...

    def save_report(self, report_id: str, fmt: str, path: str) -> None: ...

    def audit(self, action: str, detail: dict[str, Any]) -> None: ...


def analyze_memory(
    memory: list[dict[str, Any]],
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    findings = findings or []
    categories = Counter(finding.get("category", "unknown") for finding in findings)
    recurring = sorted(category for category, count in categories.items() if count >= 2)
    fragile_modules = sorted(
        {
            finding.get("affected_file")
            for finding in findings
            if finding.get("affected_file") and categories[finding.get("category")] >= 2
        }
    )
    return {
        "recurring_categories": recurring,
        "fragile_modules": fragile_modules,
        "false_positive_tracking": "available via repair status false_positive",
        "risk_reduction_history": [item for item in memory if item.get("type") == "verification"],
        "memory_notes": [f"Recurring drift category observed: {category}" for category in recurring]
        or ["No recurring drift pattern has enough evidence yet."],
    }


def generate_reports(
    *,
    store: LocalReportStore | None = None,
    report_dir: Path | str | None = None,
) -> list[dict[str, str]]:
    active_store = store if store is not None else LocalStore(DB_PATH)
    output_dir = Path(report_dir) if report_dir is not None else REPORT_DIR
    findings = active_store.payloads("findings")
    memory = active_store.payloads("memory")
    payload = {
        "scan": active_store.latest_scan(),
        "findings": findings,
        "drift": active_store.payloads("drift_events"),
        "repairs": active_store.payloads("repairs"),
        "memory": memory,
        "memory_analysis": analyze_memory(memory, findings),
        "verification": active_store.payloads("verification"),
        "policy": active_store.policy(),
        "audit": active_store.rows("audit_log")[:50],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    owner = (
        "# NICO Owner Report\n\n"
        f"Findings: {len(findings)}\n"
        f"Repair candidates: {len(payload['repairs'])}\n\n## What to fix first\n"
        + "\n".join(
            f"- RYE {repair.get('rye_score')}: {repair.get('exact_issue')}"
            for repair in payload["repairs"][:3]
        )
        + "\n"
    )
    developer = "# NICO Developer Report\n\n" + "\n".join(
        f"## {finding.get('title')}\n"
        f"- File: {finding.get('affected_file')}:{finding.get('affected_line')}\n"
        f"- Severity: {finding.get('severity')}\n"
        f"- Masked evidence: `{finding.get('masked_evidence', '')}`\n"
        f"- Fix: {finding.get('recommended_fix')}\n"
        f"- Verify: {finding.get('verification_method')}"
        for finding in findings[:50]
    )
    reparodynamic = (
        "# NICO Reparodynamic Report\n\n## Drift\n"
        + "\n".join(
            f"- {event.get('type')}: {event.get('description')}" for event in payload["drift"]
        )
        + "\n\n## RYE/TGRM\n"
        + "\n".join(
            f"- {repair.get('repair_type')} | RYE {repair.get('rye_score')} | {repair.get('exact_issue')}"
            for repair in payload["repairs"][:20]
        )
        + "\n"
    )
    compliance = (
        "# NICO Compliance Report\n\nLocal mapping only. This is not a certification report.\n\n"
        + "\n".join(
            f"- {mapping}: {finding.get('title')}"
            for finding in findings
            for mapping in finding.get("standards_mapping", [])
        )
    )
    outputs = {
        "json": json.dumps(payload, indent=2, sort_keys=True),
        "markdown": (
            "# NICO Reparodynamic Security Report\n\n"
            f"Findings: {len(findings)}\n"
            f"Drift events: {len(payload['drift'])}\n"
            f"Repair candidates: {len(payload['repairs'])}\n"
        ),
        "html": (
            "<html><body><h1>NICO Security Report</h1><pre>"
            + json.dumps(payload, indent=2)
            + "</pre></body></html>"
        ),
        "owner": owner,
        "developer": developer,
        "reparodynamic": reparodynamic,
        "compliance": compliance,
    }
    paths: list[dict[str, str]] = []
    for fmt, body in outputs.items():
        suffix = (
            "md"
            if fmt == "markdown"
            else "html"
            if fmt == "html"
            else "json"
            if fmt == "json"
            else f"{fmt}.md"
        )
        path = output_dir / f"latest.{suffix}"
        path.write_text(body, encoding="utf-8")
        active_store.save_report(f"latest-{fmt}", fmt, str(path))
        paths.append({"format": fmt, "path": str(path)})
    active_store.audit("reports.generate", {"reports": paths})
    return paths


def report_text(
    kind: str,
    *,
    store: LocalReportStore | None = None,
    report_dir: Path | str | None = None,
) -> str:
    active_store = store if store is not None else LocalStore(DB_PATH)
    output_dir = Path(report_dir) if report_dir is not None else REPORT_DIR
    generate_reports(store=active_store, report_dir=output_dir)
    mapping = {
        "owner": "owner.md",
        "developer": "developer.md",
        "reparodynamic": "reparodynamic.md",
        "compliance": "compliance.md",
    }
    path = output_dir / mapping.get(kind, "latest.md")
    return path.read_text(encoding="utf-8") if path.exists() else ""


__all__ = ["LocalReportStore", "analyze_memory", "generate_reports", "report_text"]
