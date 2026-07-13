from __future__ import annotations

import json
import shutil
from collections import Counter
from typing import Any

from nico.cli import Store, decide_action
from nico.local_reporting_service import generate_reports
from nico.local_runtime_config import DRIFT_REPO, SAMPLE_REPO, TEST_LAB
from nico.local_scan_engine import (
    detect_drift,
    make_baseline,
    new_id,
    now,
    scan_repo,
    scanner_availability,
)
from nico.local_scoring_repair_service import apply_rye, repairs_for


def ensure_test_lab() -> None:
    SAMPLE_REPO.mkdir(parents=True, exist_ok=True)
    (TEST_LAB / "mock_logs").mkdir(parents=True, exist_ok=True)
    (SAMPLE_REPO / "app.py").write_text(
        "from flask import Flask, request\n"
        "app=Flask(__name__)\n"
        "FAKE_API_KEY='FAKE_TEST_ONLY_API_KEY_1234567890'\n"
        "def admin_users(): return 'admin users'\n"
        "def calc(): return str(eval(request.args.get('q','1+1')))\n"
        "if __name__=='__main__': app.run(debug=True)\n",
        encoding="utf-8",
    )
    (SAMPLE_REPO / "webhook.py").write_text(
        "def handle_webhook(payload, headers):\n"
        "    # TODO: verify signature\n"
        "    return {'accepted': True}\n",
        encoding="utf-8",
    )
    (SAMPLE_REPO / "upload.py").write_text(
        "def save_upload(file):\n"
        "    # TODO: validate upload\n"
        "    return f'/tmp/{file.filename}'\n",
        encoding="utf-8",
    )
    (SAMPLE_REPO / "ai_agent.py").write_text("over_permissive_tools = True\n", encoding="utf-8")
    (SAMPLE_REPO / "requirements.txt").write_text("flask==0.12\nrequests==2.31.0\n", encoding="utf-8")
    (SAMPLE_REPO / "package.json").write_text(
        '{"dependencies":{"lodash":"4.17.15"}}\n',
        encoding="utf-8",
    )
    events = [json.dumps({"event": "failed_login", "username": "admin"}) for _ in range(6)]
    events.extend(
        [
            json.dumps({"event": "admin_role_change", "username": "unknown"}),
            json.dumps({"event": "api_request_spike", "count": 5000}),
        ]
    )
    (TEST_LAB / "mock_logs" / "auth.jsonl").write_text("\n".join(events) + "\n", encoding="utf-8")


def run_scan(target: str, kind: str = "local") -> dict[str, Any]:
    store = Store()
    decision = decide_action("scan", store.policy())
    if not decision["allowed"]:
        raise RuntimeError("scan blocked by governance: " + decision["reason"])

    scan = scan_repo(target)
    memory = store.payloads("memory")
    scan["findings"] = apply_rye(scan["findings"], memory)
    baseline = store.baseline() or make_baseline(scan)
    drift = detect_drift(baseline, scan)
    repairs = repairs_for(scan["findings"], memory)

    store.save_scan(scan, kind)
    store.save_drift(scan["id"], drift)
    store.save_repairs(repairs)
    store.save_baseline(baseline)
    store.save_memory(
        {
            "id": new_id("mem"),
            "type": "scan_cycle",
            "created_at": now(),
            "scan_id": scan["id"],
            "finding_count": len(scan["findings"]),
            "drift_count": len(drift),
            "repair_count": len(repairs),
            "top_categories": Counter(finding["category"] for finding in scan["findings"]).most_common(5),
        }
    )
    store.audit(
        "scan.run",
        {
            "target": target,
            "kind": kind,
            "findings": len(scan["findings"]),
            "drift": len(drift),
            "repairs": len(repairs),
        },
    )
    generate_reports()
    return {"scan": scan, "baseline": baseline, "drift": drift, "repairs": repairs}


def scan_test_lab() -> dict[str, Any]:
    ensure_test_lab()
    return run_scan(str(TEST_LAB), "test_lab")


def scan_drift_demo() -> dict[str, Any]:
    ensure_test_lab()
    shutil.rmtree(DRIFT_REPO, ignore_errors=True)
    shutil.copytree(SAMPLE_REPO, DRIFT_REPO)
    store = Store()
    clean = scan_repo(str(SAMPLE_REPO))
    clean["findings"] = apply_rye(clean["findings"], store.payloads("memory"))
    store.save_baseline(make_baseline(clean))
    (DRIFT_REPO / "new_admin_route.py").write_text(
        "admin_secret='FAKE_TEST_ONLY_ADMIN_TOKEN_0000'\n# TODO: add rate limiting\n",
        encoding="utf-8",
    )
    return run_scan(str(DRIFT_REPO), "drift_demo")


__all__ = [
    "run_scan",
    "scan_test_lab",
    "scan_drift_demo",
    "scanner_availability",
]
