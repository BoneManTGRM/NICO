from __future__ import annotations

import os
import uvicorn
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from nico.cli import (
    REPORT_DIR,
    Store,
    generate_reports,
    memory_summary,
    run_scan,
    scan_drift_demo,
    scan_test_lab,
    scanner_availability,
    verify_latest,
    verify_repair_by_id,
)

class LocalScanRequest(BaseModel):
    path: str

class PolicyLevelRequest(BaseModel):
    level: int

app = FastAPI(title="NICO API", version="0.2.0", description="Local-first defensive repair-first cybersecurity API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("NICO_ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def report_body(kind: str) -> str:
    generate_reports()
    candidates = [REPORT_DIR / f"latest.{kind}.md", REPORT_DIR / f"{kind}.md", REPORT_DIR / "latest.md"]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8")
    return ""

@app.get("/health")
def health(): return {"status":"ok","system":"NICO","mode":"local","version":"0.2.0"}
@app.post("/scan/test-lab")
def api_scan_test_lab(): return scan_test_lab()
@app.post("/scan/drift-demo")
def api_scan_drift_demo(): return scan_drift_demo()
@app.post("/scan/local")
def api_scan_local(req: LocalScanRequest):
    if not req.path: raise HTTPException(400, "path required")
    return run_scan(req.path)
@app.get("/scans/latest")
def latest_scan(): return Store().latest_scan()
@app.get("/findings")
def findings(): return Store().payloads("findings")
@app.get("/findings/{finding_id}")
def finding(finding_id: str):
    for f in Store().payloads("findings"):
        if f.get("id") == finding_id or f.get("finding_id") == finding_id: return f
    raise HTTPException(404, "finding not found")
@app.get("/drift")
def drift(): return Store().payloads("drift_events")
@app.get("/repairs")
def repairs(): return Store().payloads("repairs")
@app.get("/repairs/{repair_id}")
def repair(repair_id: str):
    for r in Store().payloads("repairs"):
        if r.get("id") == repair_id or r.get("repair_id") == repair_id: return r
    raise HTTPException(404, "repair not found")
@app.get("/verification/latest")
def verification_latest_get(): return Store().latest_verification() or verify_latest()
@app.post("/verification/latest")
def verification_latest_post(): return verify_latest()
@app.post("/verification/repair/{repair_id}")
def verification_repair_post(repair_id: str): return verify_repair_by_id(repair_id)
@app.get("/memory")
def memory(): return memory_summary()
@app.get("/reports")
def reports(): return Store().rows("reports")
@app.get("/reports/latest")
def report_latest():
    rows=Store().rows("reports"); return rows[0] if rows else {}
@app.post("/reports/generate")
def report_generate(): return generate_reports()
@app.get("/reports/owner")
def report_owner(): return Response(report_body("owner"), media_type="text/markdown")
@app.get("/reports/developer")
def report_developer(): return Response(report_body("developer"), media_type="text/markdown")
@app.get("/reports/reparodynamic")
def report_reparodynamic(): return Response(report_body("reparodynamic"), media_type="text/markdown")
@app.get("/reports/compliance")
def report_compliance(): return Response(report_body("compliance"), media_type="text/markdown")
@app.get("/policy")
def policy(): return Store().policy()
@app.post("/policy/autonomy-level")
def set_policy(req: PolicyLevelRequest):
    s=Store(); p=s.policy(); p["autonomy_level"]=max(0,min(5,int(req.level))); s.save_policy(p); s.audit("policy.autonomy_level", {"level":p["autonomy_level"]}); return p
@app.get("/audit-log")
def audit_log(): return Store().rows("audit_log")
@app.get("/scanner-availability")
def api_scanner_availability(): return scanner_availability()

def start():
    uvicorn.run("nico.api.main:app", host=os.getenv("NICO_API_HOST","127.0.0.1"), port=int(os.getenv("NICO_API_PORT","8000")), reload=False)
