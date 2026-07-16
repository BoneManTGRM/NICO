from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


RUN_ID = "midrun_df6d55c9c7fd45b2"
BASE = "https://app.nicoaudit.com/api/nico"
SCOPES = [
    {"customer_id": "default_customer", "project_id": "default_project"},
    {"customer_id": "customer_cody_jenkins", "project_id": "project_nico"},
    {"customer_id": "customer_cody_jenkins", "project_id": "project_nico_audit"},
]


def _get(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "NICO-read-only-mid-report-probe"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def _summary(body: str) -> dict:
    payload = json.loads(body)
    assessment = payload.get("assessment") if isinstance(payload.get("assessment"), dict) else {}
    manifest = payload.get("report_quality_manifest") if isinstance(payload.get("report_quality_manifest"), dict) else {}
    sections = assessment.get("sections") if isinstance(assessment.get("sections"), list) else []
    return {
        "status": payload.get("status"),
        "run_id": payload.get("run_id"),
        "customer_id": payload.get("customer_id"),
        "project_id": payload.get("project_id"),
        "scanner": payload.get("scanner"),
        "scanner_evidence_status": (payload.get("scanner_evidence") or {}).get("status") if isinstance(payload.get("scanner_evidence"), dict) else None,
        "report_generation_status": payload.get("report_generation_status"),
        "report_generation_error": payload.get("report_generation_error"),
        "report_quality_blockers": payload.get("report_quality_blockers"),
        "report_quality_issues": [
            {
                "severity": item.get("severity"),
                "code": item.get("code"),
                "section_id": item.get("section_id"),
                "message": item.get("message"),
            }
            for item in manifest.get("issues", [])
            if isinstance(item, dict)
        ],
        "report_quality_checks": manifest.get("checks"),
        "mid_report": payload.get("mid_report"),
        "maturity_signal": assessment.get("maturity_signal"),
        "evidence_coverage": assessment.get("evidence_coverage"),
        "sections": [
            {
                "id": item.get("id"),
                "truth_status": item.get("truth_status"),
                "evidence": item.get("evidence"),
                "verified_claims": item.get("verified_claims"),
                "unavailable": item.get("unavailable"),
                "missing_evidence_sources": item.get("missing_evidence_sources"),
                "failed_evidence_tools": item.get("failed_evidence_tools"),
                "unverified_claims": item.get("unverified_claims"),
                "scope_disclosures": item.get("scope_disclosures"),
            }
            for item in sections
            if isinstance(item, dict)
        ],
        "progress": [
            {
                "step": item.get("step"),
                "status": item.get("status"),
                "message": item.get("message"),
                "evidence": item.get("evidence"),
            }
            for item in payload.get("progress", [])
            if isinstance(item, dict)
        ],
        "persistence": payload.get("persistence"),
    }


def test_capture_exact_mid_report_quality_payload() -> None:
    results = []
    for scope in SCOPES:
        query = urllib.parse.urlencode(scope)
        try:
            status, body = _get(f"{BASE}/assessment/mid-run/{RUN_ID}/live-status?{query}")
            results.append({
                "scope": scope,
                "http_status": status,
                "summary": _summary(body) if status == 200 else json.loads(body),
            })
        except Exception as exc:
            results.append({"scope": scope, "probe_error": type(exc).__name__})
    try:
        status, body = _get(f"{BASE}/diagnostics/mid-runtime")
        results.append({"kind": "runtime", "http_status": status, "summary": json.loads(body)})
    except Exception as exc:
        results.append({"kind": "runtime", "probe_error": type(exc).__name__})
    raise AssertionError("NICO_MID_DF6D55C9_PROBE=" + json.dumps(results, sort_keys=True))
