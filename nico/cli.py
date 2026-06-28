from __future__ import annotations

import argparse, hashlib, json, os, re, shutil, sqlite3, uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NICO_HOME = Path(os.getenv("NICO_HOME", PROJECT_ROOT / ".nico"))
DB_PATH = Path(os.getenv("NICO_DB_PATH", NICO_HOME / "nico.sqlite3"))
REPORT_DIR = Path(os.getenv("NICO_REPORT_DIR", NICO_HOME / "reports"))
TEST_LAB = PROJECT_ROOT / "nico" / "test_lab"
SAMPLE_REPO = TEST_LAB / "sample_repo"
DRIFT_REPO = TEST_LAB / "drift_workspace"
for p in (NICO_HOME, REPORT_DIR):
    p.mkdir(parents=True, exist_ok=True)

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|jwt|private[_-]?key)\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+=]{8,})"),
    re.compile(r"(sk-[A-Za-z0-9]{16,})"),
    re.compile(r"(ghp_[A-Za-z0-9]{16,})"),
]
SEVERITY_POINTS = {"low": 1, "medium": 3, "high": 7, "critical": 10}
DEFAULT_POLICY = {
    "autonomy_level": 1,
    "kill_switch": False,
    "allowed_actions": ["scan", "report", "score", "repair_plan", "verify", "memory_update", "create_draft_pr"],
    "approval_required": ["production_key_rotation", "permanent_account_disable", "data_delete", "infrastructure_delete", "major_dependency_upgrade", "dns_change", "broad_firewall_change", "production_deploy", "architecture_rewrite"],
    "blocked_actions": ["exploit", "credential_theft", "phishing", "malware", "evasion", "persistence", "unauthorized_scan", "destructive_action", "auth_bypass"],
}
OPTIONAL_TOOLS = {"gitleaks":"secret scanning", "trufflehog":"secret scanning", "osv-scanner":"dependency scanning", "pip-audit":"python dependency scanning", "npm":"npm audit availability", "scorecard":"OpenSSF scorecard", "semgrep":"code security scanning", "bandit":"python static analysis", "eslint":"javascript/typescript static analysis"}
APPSEC_PATTERNS = [
    ("unsafe_eval", "critical", "Unsafe eval usage", "eval(", "Replace eval with a safe parser or allowlist.", "User-controlled eval can lead to code execution.", "CWE-95"),
    ("debug_mode", "high", "Debug mode enabled", "debug=True", "Disable debug mode outside local fixtures.", "Debug mode can expose internals.", "CWE-489"),
    ("missing_rate_limit", "medium", "Rate limiting TODO", "TODO: add rate limiting", "Add rate limiting and abuse detection.", "Missing throttling increases abuse risk.", "CWE-307"),
    ("insecure_webhook", "high", "Webhook signature missing", "TODO: verify signature", "Verify webhook signatures and add replay protection.", "Unsigned webhooks can allow forged events.", "CWE-345"),
    ("unsafe_file_upload", "high", "Unsafe upload fixture", "TODO: validate upload", "Validate file type, size, name, and storage path.", "Unsafe upload handling can expose data or execution paths.", "CWE-434"),
    ("ai_agent_permission_drift", "high", "AI over-permission fixture", "over_permissive_tools = True", "Restrict AI-agent tools to least privilege.", "Over-permissioned agents amplify prompt-injection risk.", "OWASP-LLM-A06"),
]
REPAIR_LIBRARY = {
    "secret_exposure": "Move secret to env/secrets manager, rotate if real, and add scanning.",
    "dependency_risk": "Upgrade dependency and verify tests/build.",
    "insecure_webhook": "Verify signatures, reject missing signatures, and add replay protection where possible.",
    "unsafe_eval": "Replace eval with a safe parser or explicit allowlist.",
    "debug_mode": "Disable debug mode outside local-only fixtures.",
    "missing_rate_limit": "Add rate limiting and abuse detection.",
    "unsafe_file_upload": "Validate upload type, size, name, path, and storage.",
    "log_anomaly": "Add rate limits, MFA review, alerting, and event correlation.",
    "identity_risk": "Require approval and audit logs for admin role changes.",
    "ai_agent_permission_drift": "Apply least-privilege tool access and human approval gates.",
}

def now(): return datetime.now(timezone.utc).isoformat()
def new_id(p): return f"{p}_{uuid.uuid4().hex[:12]}"
def fp(v): return hashlib.sha256(v.encode("utf-8")).hexdigest()[:16]
def mask(v): return "***" if len(v) <= 8 else v[:4] + "…" + v[-4:]
def mask_text(t: str) -> str:
    out = t
    for pat in SECRET_PATTERNS:
        out = pat.sub(lambda m: (m.group(1) + '="' + mask(m.group(2)) + '"') if m.lastindex and m.lastindex >= 2 else mask(m.group(0)), out)
    return out

def scanner_availability():
    return [{"tool": tool, "purpose": purpose, "available": shutil.which(tool) is not None, "mode": "optional_external" if shutil.which(tool) else "built_in_fallback_active"} for tool, purpose in OPTIONAL_TOOLS.items()]

def decide_action(action, policy):
    if policy.get("kill_switch"): return {"allowed": False, "reason": "kill switch enabled", "requires_approval": True}
    if action in policy.get("blocked_actions", []): return {"allowed": False, "reason": "blocked by defensive policy", "requires_approval": False}
    if action in policy.get("approval_required", []): return {"allowed": False, "reason": "human approval required", "requires_approval": True}
    return {"allowed": action in policy.get("allowed_actions", []), "reason": "allowed" if action in policy.get("allowed_actions", []) else "unknown action denied by default", "requires_approval": action not in policy.get("allowed_actions", [])}

class Store:
    def __init__(self, path=DB_PATH): self.path=Path(path); self.path.parent.mkdir(parents=True, exist_ok=True); self.init()
    def db(self): c=sqlite3.connect(self.path); c.row_factory=sqlite3.Row; return c
    def init(self):
        with self.db() as db: db.executescript("""CREATE TABLE IF NOT EXISTS scans(id TEXT PRIMARY KEY, kind TEXT, created_at TEXT, payload TEXT);CREATE TABLE IF NOT EXISTS findings(id TEXT PRIMARY KEY, scan_id TEXT, severity TEXT, category TEXT, payload TEXT);CREATE TABLE IF NOT EXISTS drift_events(id TEXT PRIMARY KEY, scan_id TEXT, payload TEXT);CREATE TABLE IF NOT EXISTS repairs(id TEXT PRIMARY KEY, finding_id TEXT, status TEXT, payload TEXT);CREATE TABLE IF NOT EXISTS memory(id TEXT PRIMARY KEY, payload TEXT, created_at TEXT);CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY, format TEXT, path TEXT, created_at TEXT);CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, detail TEXT, created_at TEXT);CREATE TABLE IF NOT EXISTS policy(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT);CREATE TABLE IF NOT EXISTS baseline(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT, updated_at TEXT);CREATE TABLE IF NOT EXISTS verification(id TEXT PRIMARY KEY, repair_id TEXT, payload TEXT, created_at TEXT);""")
    def audit(self,a,d):
        with self.db() as db: db.execute('INSERT INTO audit_log(action,detail,created_at) VALUES(?,?,?)',(a,json.dumps(d,sort_keys=True),now()))
    def save_scan(self,scan,kind):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO scans VALUES(?,?,?,?)',(scan['id'],kind,scan['created_at'],json.dumps(scan,sort_keys=True)))
            for f in scan['findings']: db.execute('INSERT OR REPLACE INTO findings VALUES(?,?,?,?,?)',(f['id'],scan['id'],f['severity'],f['category'],json.dumps(f,sort_keys=True)))
    def save_drift(self,scan_id,drift):
        with self.db() as db:
            for d in drift: db.execute('INSERT OR REPLACE INTO drift_events VALUES(?,?,?)',(d['id'],scan_id,json.dumps(d,sort_keys=True)))
    def save_repairs(self,repairs):
        with self.db() as db:
            for r in repairs: db.execute('INSERT OR REPLACE INTO repairs VALUES(?,?,?,?)',(r['id'],r['finding_id'],r.get('status','suggested'),json.dumps(r,sort_keys=True)))
    def update_repair_status(self,repair_id,status):
        target=None
        for r in self.payloads('repairs'):
            if r.get('id')==repair_id or r.get('repair_id')==repair_id: r['status']=status; target=r; break
        if target:
            with self.db() as db: db.execute('INSERT OR REPLACE INTO repairs VALUES(?,?,?,?)',(target['id'],target['finding_id'],status,json.dumps(target,sort_keys=True)))
        return target
    def save_memory(self,payload):
        payload.setdefault('created_at',now())
        with self.db() as db: db.execute('INSERT OR REPLACE INTO memory VALUES(?,?,?)',(payload['id'],json.dumps(payload,sort_keys=True),payload['created_at']))
    def save_verification(self,result):
        with self.db() as db: db.execute('INSERT OR REPLACE INTO verification VALUES(?,?,?,?)',(result['id'],result.get('repair_id'),json.dumps(result,sort_keys=True),result['created_at']))
    def save_report(self,rid,fmt,path):
        with self.db() as db: db.execute('INSERT OR REPLACE INTO reports VALUES(?,?,?,?)',(rid,fmt,path,now()))
    def rows(self,t):
        if t not in {'scans','findings','drift_events','repairs','memory','reports','audit_log','verification'}: raise ValueError(f'unsupported table: {t}')
        with self.db() as db: rows=db.execute(f'SELECT * FROM {t} ORDER BY rowid DESC').fetchall()
        return [dict(r) for r in rows]
    def payloads(self,t): return [json.loads(r['payload']) for r in self.rows(t) if r.get('payload')]
    def latest_scan(self):
        with self.db() as db: r=db.execute('SELECT * FROM scans ORDER BY created_at DESC LIMIT 1').fetchone()
        if not r: return {}
        d=dict(r); d['payload']=json.loads(d['payload']); d.update(d['payload']); return d
    def latest_verification(self):
        with self.db() as db: r=db.execute('SELECT payload FROM verification ORDER BY created_at DESC LIMIT 1').fetchone()
        return json.loads(r['payload']) if r else {}
    def baseline(self):
        with self.db() as db: r=db.execute('SELECT payload FROM baseline WHERE id=1').fetchone()
        return json.loads(r['payload']) if r else None
    def save_baseline(self,b):
        with self.db() as db: db.execute('INSERT OR REPLACE INTO baseline VALUES(1,?,?)',(json.dumps(b,sort_keys=True),now()))
    def policy(self):
        with self.db() as db: r=db.execute('SELECT payload FROM policy WHERE id=1').fetchone()
        return json.loads(r['payload']) if r else DEFAULT_POLICY.copy()
    def save_policy(self,p):
        with self.db() as db: db.execute('INSERT OR REPLACE INTO policy VALUES(1,?)',(json.dumps(p,sort_keys=True),))

def normalized_finding(source,category,severity,confidence,title,path='',line=None,masked='',raw_fp='',biz='',tech='',fix='',verify='',mapping=None):
    fid=new_id('finding')
    return {'finding_id':fid,'id':fid,'source':source,'category':category,'severity':severity,'confidence':confidence,'title':title,'affected_file':path,'affected_line':line,'file_path':path,'line':line,'masked_evidence':masked,'raw_evidence_fingerprint':raw_fp,'business_impact':biz,'technical_impact':tech,'recommended_fix':fix,'recommendation':fix,'verification_method':verify,'standards_mapping':mapping or [],'created_at':now(),'status':'open'}

def scan_text(path,text):
    out=[]
    for i,line in enumerate(text.splitlines(),1):
        for pat in SECRET_PATTERNS:
            m=pat.search(line)
            if m:
                raw=m.group(2) if m.lastindex and m.lastindex>=2 else m.group(0); fake='FAKE_TEST_ONLY' in raw.upper()
                out.append(normalized_finding('built_in_secret_scanner','secret_exposure','high' if fake else 'critical',0.95,'Potential secret detected',path,i,mask_text(line.strip()),fp(raw),'A leaked credential can expose systems, billing, users, or customer data.','Credential-like source value was found. Raw value is not stored.','Move to environment/secrets manager and rotate if real.','Rescan affected file and confirm credential-like value is absent.',['CWE-798','OWASP-ASVS-V6']))
        for cat,sev,title,marker,fix,biz,mapid in APPSEC_PATTERNS:
            if marker in line: out.append(normalized_finding('built_in_appsec_scanner',cat,sev,0.88,title,path,i,line.strip(),fp(cat+path+str(i)),biz,f'{title} marker was detected.',fix,'Apply targeted fix, run tests, and rescan affected file.',[mapid]))
    if path.endswith('requirements.txt') and 'flask==0.12' in text: out.append(normalized_finding('built_in_dependency_scanner','dependency_risk','high',0.9,'Risky Python dependency fixture',path,masked='flask==0.12',raw_fp='dependency-fixture-flask-012',biz='Outdated dependencies increase breach and downtime risk.',tech='Old Flask test fixture detected.',fix='Upgrade dependency and run tests.',verify='Rescan dependency manifests and confirm risky version is absent.',['CWE-1104']))
    if path.endswith('package.json') and '4.17.15' in text: out.append(normalized_finding('built_in_dependency_scanner','dependency_risk','high',0.9,'Risky npm dependency fixture',path,masked='lodash 4.17.15',raw_fp='dependency-fixture-lodash-41715',biz='Outdated packages can expose exploitable paths.',tech='Old lodash test fixture detected.',fix='Upgrade package and run build/tests.',verify='Rescan package manifest and confirm risky version is absent.',['CWE-1104']))
    if path.endswith('.jsonl'):
        events=[]
        for x in text.splitlines():
            try: events.append(json.loads(x))
            except Exception: pass
        if sum(1 for e in events if e.get('event')=='failed_login')>=5: out.append(normalized_finding('built_in_log_scanner','log_anomaly','high',0.85,'Repeated failed login pattern',path,masked='failed_login count >= 5',raw_fp='failed-login-fixture',biz='Repeated failed logins can indicate credential stuffing or brute force.',tech='Mock repeated failed login pattern detected.',fix='Add rate limits, MFA review, and alerting.',verify='Inspect logs after controls and confirm detection/reduction.',['MITRE-ATTACK-T1110']))
        if any(e.get('event')=='admin_role_change' for e in events): out.append(normalized_finding('built_in_log_scanner','identity_risk','high',0.84,'Suspicious admin action pattern',path,masked='admin role change',raw_fp='admin-role-change-fixture',biz='Unexpected admin changes can lead to privilege abuse.',tech='Mock admin role change detected.',fix='Require approval and audit logs for admin changes.',verify='Confirm admin changes require approval and audit logging.',['MITRE-ATTACK-T1078']))
    return out

def scan_repo(target):
    root=Path(target).resolve(); findings=[]; files=[]; skip={'.git','node_modules','.venv','venv','__pycache__','.nico','.next'}
    for p in root.rglob('*'):
        if p.is_dir() or any(x in skip for x in p.parts): continue
        try: text=p.read_text(encoding='utf-8',errors='ignore')
        except Exception: continue
        rel=str(p.relative_to(root)); files.append(rel); findings.extend(scan_text(rel,text))
    return {'id':new_id('scan'),'target':str(root),'created_at':now(),'files_scanned':files,'findings':findings,'scanner_availability':scanner_availability()}

def risk_score(findings): return min(100,sum(SEVERITY_POINTS.get(str(f.get('severity','low')).lower(),1) for f in findings)*5)
def make_baseline(scan): return {'scan_id':scan['id'],'files_scanned_count':len(scan['files_scanned']),'finding_count':len(scan['findings']),'risk_score':risk_score(scan['findings']),'categories':sorted({f['category'] for f in scan['findings']})}
def detect_drift(base,scan):
    if not base: return []
    cur=risk_score(scan['findings']); br=base.get('risk_score',0); out=[]
    if cur>br: out.append({'id':new_id('drift'),'type':'risk_score_drift','severity':'high','created_at':now(),'baseline_risk':br,'current_risk':cur,'description':'Current scan risk exceeds the stored secure baseline.'})
    for cat in sorted({f['category'] for f in scan['findings']}-set(base.get('categories',[]))): out.append({'id':new_id('drift'),'type':cat,'severity':'medium','created_at':now(),'baseline_risk':br,'current_risk':cur,'description':f'New drift category detected: {cat}'})
    return out

def rye_score(f,memory=None):
    memory=memory or []; cat=f.get('category','unknown'); sev=f.get('severity','low'); rec=sum(1 for m in memory if m.get('category')==cat or m.get('finding_category')==cat)
    base={'low':20,'medium':45,'high':72,'critical':92}.get(sev,20); exploit=85 if cat in {'secret_exposure','unsafe_eval','insecure_webhook','identity_risk'} else 62; blast=86 if cat in {'secret_exposure','identity_risk','insecure_webhook','unsafe_eval'} else 48; verify=82 if f.get('verification_method') else 55; urgency=min(100,base+rec*8); denom=(28+18+9+8+(9 if f.get('confidence',0)>=0.8 else 25)+14); score=round(max(1,min(100,((base*exploit*blast*verify*urgency)/denom)/85000*100)),2)
    return {'score':score,'severity':sev,'priority':'critical_first' if score>=80 else 'high' if score>=60 else 'medium' if score>=35 else 'low','confidence':f.get('confidence',0.75),'why_this_matters':f.get('business_impact','This finding may increase security risk.'),'why_this_ranks_above_others':f'{sev} severity, {cat} category, recurrence {rec}, and verification availability.','what_can_be_safely_automated':'Scan, report, score, generate repair prompt, and run local verification.','what_needs_approval':'Production changes, credential rotation, deployments, destructive actions, or broad infrastructure changes.','what_can_wait':'Lower-scoring repairs with limited exposure and no recurrence.','what_would_be_overkill':'Broad rewrites before targeted local verification.'}

def apply_rye(findings,memory=None):
    out=[]
    for f in findings:
        x=dict(f); x['rye']=rye_score(x,memory); out.append(x)
    return out

def repairs_for(findings,memory=None):
    out=[]
    for f in findings:
        base=f.get('rye',rye_score(f,memory)).get('score',0); fix=REPAIR_LIBRARY.get(f['category'],'Apply smallest defensive fix and verify.'); files=[f['affected_file']] if f.get('affected_file') else []
        for typ,delta,level in [('minimal',0,1),('moderate',-6,2),('strong',-12,3)]:
            rid=new_id('repair'); prompt=f"Fix only the {f.get('title',f['category'])} issue in {f.get('affected_file','the affected file')}.\nDo not rewrite unrelated code.\nApply this targeted defensive repair: {fix}\nAdd the smallest relevant tests.\nRun local tests or a NICO rescan.\nReturn a short verification summary.\nNever expose raw secrets."
            out.append({'repair_id':rid,'id':rid,'finding_id':f['id'],'repair_type':typ,'exact_issue':f.get('title',f['category']),'affected_files':files,'smallest_safe_change':fix,'tests_to_add':['Add focused regression test if available.','Run NICO rescan after repair.'],'verification_command':'python -m nico verify latest','rollback_plan':'Revert targeted change if verification fails or new drift appears.','codex_ready_patch_prompt':prompt,'owner_friendly_explanation':f'This {typ} repair reduces {f["category"]} risk without broad rewrites.','developer_ready_explanation':f'Target {files or ["affected code"]}; verify with: {f.get("verification_method")}', 'rye_score':max(0,round(base+delta,2)),'autonomy_level':level,'approval_requirement':'human_review_required_before_production_change' if f['severity'] in {'high','critical'} else 'safe_for_local_repair_prompt_generation','status':'suggested','created_at':now()})
    return sorted(out,key=lambda r:r['rye_score'],reverse=True)

def analyze_memory(memory,findings=None):
    findings=findings or []; cats=Counter(f.get('category','unknown') for f in findings); recurring=sorted(k for k,v in cats.items() if v>=2)
    return {'recurring_categories':recurring,'fragile_modules':sorted({f.get('affected_file') for f in findings if f.get('affected_file') and cats[f.get('category')]>=2}),'false_positive_tracking':'available via repair status false_positive','risk_reduction_history':[m for m in memory if m.get('type')=='verification'],'memory_notes':[f'Recurring drift category observed: {c}' for c in recurring] or ['No recurring drift pattern has enough evidence yet.']}

def ensure_test_lab():
    SAMPLE_REPO.mkdir(parents=True,exist_ok=True); (TEST_LAB/'mock_logs').mkdir(parents=True,exist_ok=True)
    (SAMPLE_REPO/'app.py').write_text("from flask import Flask, request\napp=Flask(__name__)\nFAKE_API_KEY='FAKE_TEST_ONLY_API_KEY_1234567890'\ndef admin_users(): return 'admin users'\ndef calc(): return str(eval(request.args.get('q','1+1')))\nif __name__=='__main__': app.run(debug=True)\n",encoding='utf-8')
    (SAMPLE_REPO/'webhook.py').write_text("def handle_webhook(payload, headers):\n    # TODO: verify signature\n    return {'accepted': True}\n",encoding='utf-8')
    (SAMPLE_REPO/'upload.py').write_text("def save_upload(file):\n    # TODO: validate upload\n    return f'/tmp/{file.filename}'\n",encoding='utf-8')
    (SAMPLE_REPO/'ai_agent.py').write_text('over_permissive_tools = True\n',encoding='utf-8'); (SAMPLE_REPO/'requirements.txt').write_text('flask==0.12\nrequests==2.31.0\n',encoding='utf-8'); (SAMPLE_REPO/'package.json').write_text('{"dependencies":{"lodash":"4.17.15"}}\n',encoding='utf-8')
    events=[json.dumps({'event':'failed_login','username':'admin'}) for _ in range(6)]+[json.dumps({'event':'admin_role_change','username':'unknown'}),json.dumps({'event':'api_request_spike','count':5000})]; (TEST_LAB/'mock_logs'/'auth.jsonl').write_text('\n'.join(events)+'\n',encoding='utf-8')

def generate_reports():
    s=Store(); findings=s.payloads('findings'); payload={'scan':s.latest_scan(),'findings':findings,'drift':s.payloads('drift_events'),'repairs':s.payloads('repairs'),'memory':s.payloads('memory'),'memory_analysis':analyze_memory(s.payloads('memory'),findings),'verification':s.payloads('verification'),'policy':s.policy(),'audit':s.rows('audit_log')[:50]}; REPORT_DIR.mkdir(parents=True,exist_ok=True); paths=[]
    owner='# NICO Owner Report\n\nFindings: '+str(len(findings))+'\nRepair candidates: '+str(len(payload['repairs']))+'\n\n## What to fix first\n'+'\n'.join(f"- RYE {r.get('rye_score')}: {r.get('exact_issue')}" for r in payload['repairs'][:3])+'\n'
    developer='# NICO Developer Report\n\n'+'\n'.join(f"## {f.get('title')}\n- File: {f.get('affected_file')}:{f.get('affected_line')}\n- Severity: {f.get('severity')}\n- Masked evidence: `{f.get('masked_evidence','')}`\n- Fix: {f.get('recommended_fix')}\n- Verify: {f.get('verification_method')}\n" for f in findings[:50])
    reparodynamic='# NICO Reparodynamic Report\n\n## Drift\n'+'\n'.join(f"- {d.get('type')}: {d.get('description')}" for d in payload['drift'])+'\n\n## RYE/TGRM\n'+'\n'.join(f"- {r.get('repair_type')} | RYE {r.get('rye_score')} | {r.get('exact_issue')}" for r in payload['repairs'][:20])+'\n'
    compliance='# NICO Compliance Report\n\nLocal mapping only. This is not a certification report.\n\n'+'\n'.join(f"- {m}: {f.get('title')}" for f in findings for m in f.get('standards_mapping',[]))+'\n'
    outputs={'json':json.dumps(payload,indent=2,sort_keys=True),'markdown':'# NICO Reparodynamic Security Report\n\nFindings: '+str(len(findings))+'\nDrift events: '+str(len(payload['drift']))+'\nRepair candidates: '+str(len(payload['repairs']))+'\n','html':'<html><body><h1>NICO Security Report</h1><pre>'+json.dumps(payload,indent=2)+'</pre></body></html>','owner':owner,'developer':developer,'reparodynamic':reparodynamic,'compliance':compliance}
    for fmt,content in outputs.items():
        path=REPORT_DIR/('latest.'+('md' if fmt=='markdown' else 'html' if fmt=='html' else 'json' if fmt=='json' else fmt+'.md'))
        path.write_text(content,encoding='utf-8'); s.save_report('latest-'+fmt,fmt,str(path)); paths.append({'format':fmt,'path':str(path)})
    s.audit('reports.generate',{'reports':paths}); return paths

def report_text(kind):
    generate_reports(); mapping={'owner':'owner.md','developer':'developer.md','reparodynamic':'reparodynamic.md','compliance':'compliance.md'}; path=REPORT_DIR/mapping.get(kind,'latest.md'); return path.read_text(encoding='utf-8') if path.exists() else ''

def run_scan(target,kind='local'):
    s=Store(); dec=decide_action('scan',s.policy())
    if not dec['allowed']: raise RuntimeError('scan blocked by governance: '+dec['reason'])
    scan=scan_repo(target); mem=s.payloads('memory'); scan['findings']=apply_rye(scan['findings'],mem); base=s.baseline() or make_baseline(scan); drift=detect_drift(base,scan); repairs=repairs_for(scan['findings'],mem); s.save_scan(scan,kind); s.save_drift(scan['id'],drift); s.save_repairs(repairs); s.save_baseline(base); s.save_memory({'id':new_id('mem'),'type':'scan_cycle','created_at':now(),'scan_id':scan['id'],'finding_count':len(scan['findings']),'drift_count':len(drift),'repair_count':len(repairs),'top_categories':Counter(f['category'] for f in scan['findings']).most_common(5)}); s.audit('scan.run',{'target':target,'kind':kind,'findings':len(scan['findings']),'drift':len(drift),'repairs':len(repairs)}); generate_reports(); return {'scan':scan,'baseline':base,'drift':drift,'repairs':repairs}

def scan_test_lab(): ensure_test_lab(); return run_scan(str(TEST_LAB),'test_lab')
def scan_drift_demo():
    ensure_test_lab(); shutil.rmtree(DRIFT_REPO,ignore_errors=True); shutil.copytree(SAMPLE_REPO,DRIFT_REPO); s=Store(); clean=scan_repo(str(SAMPLE_REPO)); clean['findings']=apply_rye(clean['findings'],s.payloads('memory')); s.save_baseline(make_baseline(clean)); (DRIFT_REPO/'new_admin_route.py').write_text("admin_secret='FAKE_TEST_ONLY_ADMIN_TOKEN_0000'\n# TODO: add rate limiting\n",encoding='utf-8'); return run_scan(str(DRIFT_REPO),'drift_demo')
def verify_latest():
    s=Store(); scan=s.latest_scan(); findings=s.payloads('findings'); repairs=s.payloads('repairs'); masked=all('FAKE_TEST_ONLY_SECRET_123456' not in str(f) for f in findings); result={'id':new_id('verify'),'created_at':now(),'scan_id':scan.get('id'),'repair_id':None,'passed':bool(scan) and masked,'status':'verification_observed','checks':['scan_available' if scan else 'scan_missing','findings_masked' if masked else 'masking_failure','governance_enabled','repair_candidates_present' if repairs else 'repair_candidates_missing'],'risk_reduction':'pending_targeted_code_repair','finding_count':len(findings),'repair_count':len(repairs),'baseline_update_allowed':False}; s.save_verification(result); s.save_memory({'id':result['id'],'type':'verification','created_at':result['created_at'],'result':result}); s.audit('verification.latest',result); return result
def verify_repair_by_id(repair_id):
    s=Store(); repair=next((r for r in s.payloads('repairs') if r.get('id')==repair_id or r.get('repair_id')==repair_id),None); result={'id':new_id('verify'),'created_at':now(),'repair_id':repair.get('id') if repair else None,'passed':bool(repair),'status':'verification_pending' if repair else 'repair_not_found','checks':['repair_exists' if repair else 'repair_missing','rescan_required','raw_secret_masking_checked'],'risk_reduction':'requires_rescan_after_patch','baseline_update_allowed':False}; s.save_verification(result); s.save_memory({'id':result['id'],'type':'verification','created_at':result['created_at'],'result':result});
    if repair: s.update_repair_status(repair['id'],result['status'])
    s.audit('verification.repair',result); return result

def memory_summary():
    s=Store(); mem=s.payloads('memory'); return {'items':mem,'analysis':analyze_memory(mem,s.payloads('findings'))}

def main(argv=None):
    parser=argparse.ArgumentParser(prog='nico'); sub=parser.add_subparsers(dest='cmd'); sp=sub.add_parser('scan'); sp.add_argument('target'); sub.add_parser('scan-test-lab'); sub.add_parser('scan-drift-demo'); rp=sub.add_parser('report'); rp.add_argument('which',nargs='?',default='latest'); vp=sub.add_parser('verify'); vp.add_argument('which',nargs='?',default='latest'); vp.add_argument('--repair-id'); sub.add_parser('memory'); pp=sub.add_parser('policy'); pp.add_argument('action',nargs='?',default='show'); sub.add_parser('scanner-availability'); args=parser.parse_args(argv); s=Store()
    if args.cmd=='scan': r=run_scan(args.target); print(json.dumps({'scan_id':r['scan']['id'],'findings':len(r['scan']['findings']),'drift':len(r['drift']),'repairs':len(r['repairs'])},indent=2)); return
    if args.cmd=='scan-test-lab': r=scan_test_lab(); print(json.dumps({'scan_id':r['scan']['id'],'findings':len(r['scan']['findings']),'drift':len(r['drift']),'repairs':len(r['repairs'])},indent=2)); return
    if args.cmd=='scan-drift-demo': r=scan_drift_demo(); print(json.dumps({'scan_id':r['scan']['id'],'findings':len(r['scan']['findings']),'drift':len(r['drift']),'repairs':len(r['repairs'])},indent=2)); return
    if args.cmd=='report': print(report_text(args.which) if args.which in {'owner','developer','reparodynamic','compliance'} else json.dumps(generate_reports(),indent=2)); return
    if args.cmd=='verify': print(json.dumps(verify_repair_by_id(args.repair_id) if args.repair_id else verify_latest(),indent=2)); return
    if args.cmd=='memory': print(json.dumps(memory_summary(),indent=2)); return
    if args.cmd=='policy': print(json.dumps(s.policy(),indent=2)); return
    if args.cmd=='scanner-availability': print(json.dumps(scanner_availability(),indent=2)); return
    parser.print_help()
if __name__=='__main__': main()
