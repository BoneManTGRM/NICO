from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from nico.cli import scan_test_lab, scan_drift_demo, run_scan, Store, generate_reports, verify_latest
class LocalScanRequest(BaseModel): path: str
class PolicyLevelRequest(BaseModel): level: int
app=FastAPI(title='NICO API',version='0.1.0',description='Local-first defensive cybersecurity API')
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:3000'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
@app.get('/health')
def health(): return {'status':'ok','system':'NICO','mode':'local'}
@app.post('/scan/test-lab')
def api_scan_test_lab(): return scan_test_lab()
@app.post('/scan/drift-demo')
def api_scan_drift_demo(): return scan_drift_demo()
@app.post('/scan/local')
def api_scan_local(req:LocalScanRequest):
    if not req.path: raise HTTPException(400,'path required')
    return run_scan(req.path)
@app.get('/scans/latest')
def latest_scan(): return Store().latest_scan()
@app.get('/findings')
def findings(): return Store().payloads('findings')
@app.get('/findings/{finding_id}')
def finding(finding_id:str):
    for f in Store().payloads('findings'):
        if f.get('id')==finding_id: return f
    raise HTTPException(404,'finding not found')
@app.get('/drift')
def drift(): return Store().payloads('drift_events')
@app.get('/repairs')
def repairs(): return Store().payloads('repairs')
@app.get('/repairs/{repair_id}')
def repair(repair_id:str):
    for r in Store().payloads('repairs'):
        if r.get('id')==repair_id: return r
    raise HTTPException(404,'repair not found')
@app.get('/verification/latest')
def verification_latest(): return verify_latest()
@app.post('/verification/latest')
def verification_post(): return verify_latest()
@app.get('/memory')
def memory(): return Store().payloads('memory')
@app.get('/reports')
def reports(): return Store().rows('reports')
@app.get('/reports/latest')
def report_latest():
    rows=Store().rows('reports'); return rows[0] if rows else {}
@app.post('/reports/generate')
def report_generate(): return generate_reports()
@app.get('/policy')
def policy(): return Store().policy()
@app.post('/policy/autonomy-level')
def set_policy(req:PolicyLevelRequest):
    s=Store(); p=s.policy(); p['autonomy_level']=max(0,min(5,int(req.level))); s.save_policy(p); s.audit('policy.autonomy_level',{'level':p['autonomy_level']}); return p
@app.get('/audit-log')
def audit_log(): return Store().rows('audit_log')
def start(): uvicorn.run('nico.api.main:app',host='127.0.0.1',port=8000,reload=False)
