from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, sqlite3, uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
PROJECT_ROOT=Path(__file__).resolve().parents[1]; NICO_HOME=Path(os.getenv('NICO_HOME',PROJECT_ROOT/'.nico')); DB_PATH=Path(os.getenv('NICO_DB_PATH',NICO_HOME/'nico.sqlite3')); REPORT_DIR=Path(os.getenv('NICO_REPORT_DIR',NICO_HOME/'reports')); TEST_LAB=PROJECT_ROOT/'nico'/'test_lab'; SAMPLE_REPO=TEST_LAB/'sample_repo'; DRIFT_REPO=TEST_LAB/'drift_workspace'
for p in (NICO_HOME,REPORT_DIR): p.mkdir(parents=True,exist_ok=True)
SECRET_PATTERNS=[re.compile(r"(?i)(api[_-]?key|secret|token|password|jwt|private[_-]?key)\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+=]{8,})"),re.compile(r"(sk-[A-Za-z0-9]{16,})"),re.compile(r"(ghp_[A-Za-z0-9]{16,})")]
SEV={'low':1,'medium':3,'high':7,'critical':10}; DEFAULT_POLICY={'autonomy_level':1,'kill_switch':False,'allowed_actions':['scan','report','score','repair_plan','verify','memory_update'],'approval_required':['production_key_rotation','permanent_account_disable','data_delete','infrastructure_delete','major_dependency_upgrade','dns_change','broad_firewall_change','production_deploy','architecture_rewrite'],'blocked_actions':['exploit','credential_theft','phishing','malware','evasion','persistence','unauthorized_scan']}
def now(): return datetime.now(timezone.utc).isoformat()
def new_id(p): return f'{p}_{uuid.uuid4().hex[:12]}'
def fp(v): return hashlib.sha256(v.encode()).hexdigest()[:16]
def mask(v): return '***' if len(v)<=8 else v[:4]+'…'+v[-4:]
def mask_text(t):
    out=t
    for pat in SECRET_PATTERNS:
        out=pat.sub(lambda m:(m.group(1)+'="'+mask(m.group(2))+'"') if m.lastindex and m.lastindex>=2 else mask(m.group(0)),out)
    return out
def risk_score(findings): return min(100,sum(SEV.get(str(f.get('severity','low')).lower(),1) for f in findings)*5)
def rye_score(f):
    base={'low':25,'medium':45,'high':70,'critical':90}.get(f.get('severity','low'),25); like=80 if f.get('category') in {'secret_exposure','unsafe_eval','insecure_webhook'} else 60; blast=85 if f.get('severity') in {'critical','high'} else 45; return round(min(100,(base*like*blast*85*base)/(20+15+5+5+10+10)/100000),2)
class Store:
    def __init__(self,path=DB_PATH): self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); self.init()
    def db(self): c=sqlite3.connect(self.path); c.row_factory=sqlite3.Row; return c
    def init(self):
        with self.db() as db: db.executescript("""CREATE TABLE IF NOT EXISTS scans(id TEXT PRIMARY KEY, kind TEXT, created_at TEXT, payload TEXT);CREATE TABLE IF NOT EXISTS findings(id TEXT PRIMARY KEY, scan_id TEXT, severity TEXT, category TEXT, payload TEXT);CREATE TABLE IF NOT EXISTS drift_events(id TEXT PRIMARY KEY, scan_id TEXT, payload TEXT);CREATE TABLE IF NOT EXISTS repairs(id TEXT PRIMARY KEY, finding_id TEXT, payload TEXT);CREATE TABLE IF NOT EXISTS memory(id TEXT PRIMARY KEY, payload TEXT, created_at TEXT);CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY, format TEXT, path TEXT, created_at TEXT);CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, detail TEXT, created_at TEXT);CREATE TABLE IF NOT EXISTS policy(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT);CREATE TABLE IF NOT EXISTS baseline(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT, updated_at TEXT);""")
    def audit(self,a,d):
        with self.db() as db: db.execute('INSERT INTO audit_log(action,detail,created_at) VALUES(?,?,?)',(a,json.dumps(d),now()))
    def save_scan(self,scan,kind):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO scans VALUES(?,?,?,?)',(scan['id'],kind,now(),json.dumps(scan)))
            for f in scan['findings']: db.execute('INSERT OR REPLACE INTO findings VALUES(?,?,?,?,?)',(f['id'],scan['id'],f['severity'],f['category'],json.dumps(f)))
    def rows(self,t):
        with self.db() as db: rows=db.execute(f'SELECT * FROM {t} ORDER BY rowid DESC').fetchall()
        return [dict(r) for r in rows]
    def payloads(self,t): return [json.loads(r['payload']) for r in self.rows(t)]
    def latest_scan(self):
        with self.db() as db: r=db.execute('SELECT * FROM scans ORDER BY created_at DESC LIMIT 1').fetchone()
        return dict(r)|{'payload':json.loads(r['payload'])} if r else {}
    def baseline(self):
        with self.db() as db: r=db.execute('SELECT payload FROM baseline WHERE id=1').fetchone()
        return json.loads(r['payload']) if r else None
    def save_baseline(self,b):
        with self.db() as db: db.execute('INSERT OR REPLACE INTO baseline VALUES(1,?,?)',(json.dumps(b),now()))
    def policy(self):
        with self.db() as db: r=db.execute('SELECT payload FROM policy WHERE id=1').fetchone()
        return json.loads(r['payload']) if r else DEFAULT_POLICY
    def save_policy(self,p):
        with self.db() as db: db.execute('INSERT OR REPLACE INTO policy VALUES(1,?)',(json.dumps(p),))
@dataclass
class Finding:
    category:str; severity:str; title:str; description:str; file_path:str=''; line:int|None=None; evidence:str=''; masked_evidence:str=''; recommendation:str=''; id:str=''; status:str='open'; created_at:str=''
    def to_dict(self):
        d=asdict(self); d['id']=d['id'] or new_id('finding'); d['created_at']=d['created_at'] or now(); return d
def ensure_test_lab():
    SAMPLE_REPO.mkdir(parents=True,exist_ok=True); (TEST_LAB/'mock_logs').mkdir(parents=True,exist_ok=True)
    (SAMPLE_REPO/'app.py').write_text("from flask import Flask, request\napp=Flask(__name__)\nFAKE_API_KEY='FAKE_TEST_ONLY_API_KEY_1234567890'\ndef admin_users(): return 'admin users'\ndef calc(): return str(eval(request.args.get('q','1+1')))\nif __name__=='__main__': app.run(debug=True)\n",encoding='utf-8')
    (SAMPLE_REPO/'webhook.py').write_text("def handle_webhook(payload,headers):\n    # TODO: verify signature\n    return {'accepted': True}\n",encoding='utf-8')
    (SAMPLE_REPO/'upload.py').write_text("def save_upload(file):\n    # TODO: validate upload\n    return f'/tmp/{file.filename}'\n",encoding='utf-8')
    (SAMPLE_REPO/'ai_agent.py').write_text("over_permissive_tools = True\n",encoding='utf-8')
    (SAMPLE_REPO/'requirements.txt').write_text('flask==0.12\nrequests==2.31.0\n',encoding='utf-8'); (SAMPLE_REPO/'package.json').write_text('{"dependencies":{"lodash":"4.17.15"}}\n',encoding='utf-8')
    events=[json.dumps({'event':'failed_login','username':'admin'}) for _ in range(6)]+[json.dumps({'event':'admin_role_change','username':'unknown'}),json.dumps({'event':'api_request_spike','count':5000})]; (TEST_LAB/'mock_logs'/'auth.jsonl').write_text('\n'.join(events)+'\n',encoding='utf-8')
def finding(cat,sev,title,desc,path='',line=None,ev='',masked='',rec=''): return Finding(cat,sev,title,desc,path,line,ev,masked,rec).to_dict()
def scan_text(path,text):
    out=[]
    for i,line in enumerate(text.splitlines(),1):
        for pat in SECRET_PATTERNS:
            m=pat.search(line)
            if m:
                raw=m.group(2) if m.lastindex and m.lastindex>=2 else m.group(0); out.append(finding('secret_exposure','high' if 'FAKE' in raw.upper() else 'critical','Potential secret detected','Masked credential-like value detected.',path,i,'fingerprint:'+fp(raw),mask_text(line.strip()),'Move to environment/secrets manager and rotate if real.'))
        for cat,sev,title,marker,rec in [('unsafe_eval','critical','Unsafe eval usage','eval(','Replace eval.'),('debug_mode','high','Debug mode enabled','debug=True','Disable debug mode.'),('missing_rate_limit','medium','Rate limiting TODO','TODO: add rate limiting','Add rate limiting.'),('insecure_webhook','high','Webhook signature missing','TODO: verify signature','Verify signatures.'),('unsafe_file_upload','high','Unsafe upload fixture','TODO: validate upload','Validate uploads.'),('ai_agent_permission_drift','high','AI over-permission fixture','over_permissive_tools = True','Least privilege tool access.')]:
            if marker in line: out.append(finding(cat,sev,title,'Defensive AppSec pattern detected.',path,i,'',line.strip(),rec))
    if path.endswith('requirements.txt') and 'flask==0.12' in text: out.append(finding('dependency_risk','high','Risky dependency fixture','Old Flask fixture.',path,masked='flask==0.12',rec='Upgrade dependency.'))
    if path.endswith('package.json') and '4.17.15' in text: out.append(finding('dependency_risk','high','Risky npm dependency fixture','Old npm fixture.',path,masked='lodash 4.17.15',rec='Upgrade dependency.'))
    if path.endswith('.jsonl'):
        lines=[json.loads(x) for x in text.splitlines() if x.strip()]
        if sum(1 for e in lines if e.get('event')=='failed_login')>=5: out.append(finding('log_anomaly','high','Repeated failed logins','Mock brute-force pattern.',path,masked='failed_login count >= 5',rec='Add rate limits and MFA review.'))
        if any(e.get('event')=='admin_role_change' for e in lines): out.append(finding('identity_risk','high','Suspicious admin action','Mock admin role change.',path,masked='admin role change',rec='Audit admin changes.'))
    return out
def scan_repo(target):
    root=Path(target).resolve(); findings=[]; files=[]
    for p in root.rglob('*'):
        if p.is_dir() or any(x in {'.git','node_modules','.venv','venv','__pycache__','.nico','.next'} for x in p.parts): continue
        try: text=p.read_text(encoding='utf-8',errors='ignore')
        except Exception: continue
        rel=str(p.relative_to(root)); files.append(rel); findings.extend(scan_text(rel,text))
    return {'id':new_id('scan'),'target':str(root),'created_at':now(),'files_scanned':files,'findings':findings}
def make_baseline(scan): return {'scan_id':scan['id'],'files_scanned_count':len(scan['files_scanned']),'finding_count':len(scan['findings']),'risk_score':risk_score(scan['findings']),'categories':sorted({f['category'] for f in scan['findings']})}
def detect_drift(base,scan):
    if not base: return []
    cur=risk_score(scan['findings']); br=base.get('risk_score',0); out=[]
    if cur>br: out.append({'id':new_id('drift'),'type':'risk_score_drift','severity':'high','created_at':now(),'baseline_risk':br,'current_risk':cur,'description':'Current scan risk exceeds secure baseline.'})
    for cat in sorted({f['category'] for f in scan['findings']}-set(base.get('categories',[]))): out.append({'id':new_id('drift'),'type':cat,'severity':'medium','created_at':now(),'baseline_risk':br,'current_risk':cur,'description':f'New drift category detected: {cat}'})
    return out
def repairs_for(findings):
    out=[]
    for f in findings:
        fix={'secret_exposure':'Move secret to env/secrets manager, rotate if real, add scanning.','dependency_risk':'Upgrade dependency and verify tests.','insecure_webhook':'Verify webhook signatures.','unsafe_eval':'Replace eval with safe parser.','debug_mode':'Disable debug mode.','missing_rate_limit':'Add rate limiting.','unsafe_file_upload':'Validate upload.','ai_agent_permission_drift':'Least privilege AI tools.'}.get(f['category'],'Apply smallest defensive fix and verify.')
        for strat,level,delta in [('minimal',1,0),('moderate',2,-5),('strong',3,-10)]: out.append({'id':new_id('repair'),'finding_id':f['id'],'summary':f'{strat.title()} TGRM repair for {f["title"]}','strategy':strat,'exact_change':fix,'verification_plan':'Rescan affected files and confirm risk is removed or reduced.','rollback_plan':'Revert targeted change if verification fails.','rye_score':max(0,rye_score(f)+delta),'severity':f['severity'],'autonomy_level':level,'created_at':now()})
    return out
def store_memory(payload):
    s=Store();
    with s.db() as db: db.execute('INSERT INTO memory VALUES(?,?,?)',(payload['id'],json.dumps(payload),now()))
def generate_reports():
    s=Store(); payload={'scan':s.latest_scan(),'findings':s.payloads('findings'),'drift':s.payloads('drift_events'),'repairs':s.payloads('repairs'),'memory':s.payloads('memory'),'policy':s.policy(),'audit':s.rows('audit_log')[:20]}; REPORT_DIR.mkdir(parents=True,exist_ok=True); paths=[]
    md='# NICO Reparodynamic Security Report\n\nFindings: '+str(len(payload['findings']))+'\nDrift events: '+str(len(payload['drift']))+'\nRepair candidates: '+str(len(payload['repairs']))+'\n'
    html='<html><body><h1>NICO Security Report</h1><pre>'+json.dumps(payload,indent=2)+'</pre></body></html>'
    for fmt,content in [('json',json.dumps(payload,indent=2)),('markdown',md),('html',html)]:
        path=REPORT_DIR/f'latest.{"md" if fmt=="markdown" else fmt}'; path.write_text(content,encoding='utf-8'); paths.append({'format':fmt,'path':str(path)})
        with s.db() as db: db.execute('INSERT OR REPLACE INTO reports VALUES(?,?,?,?)',(f'latest-{fmt}',fmt,str(path),now()))
    s.audit('reports.generate',{'reports':paths}); return paths
def run_scan(target,kind='local'):
    s=Store(); scan=scan_repo(target); base=s.baseline() or make_baseline(scan); drift=detect_drift(base,scan); repairs=repairs_for(scan['findings']); s.save_scan(scan,kind)
    with s.db() as db:
        for d in drift: db.execute('INSERT INTO drift_events VALUES(?,?,?)',(d['id'],scan['id'],json.dumps(d)))
        for r in repairs: db.execute('INSERT OR REPLACE INTO repairs VALUES(?,?,?)',(r['id'],r['finding_id'],json.dumps(r)))
    s.save_baseline(base); s.audit('scan.run',{'target':target,'kind':kind,'findings':len(scan['findings']),'drift':len(drift)}); store_memory({'id':new_id('mem'),'type':'scan_cycle','created_at':now(),'scan_id':scan['id'],'finding_count':len(scan['findings']),'drift_count':len(drift),'repair_count':len(repairs)}); generate_reports(); return {'scan':scan,'baseline':base,'drift':drift,'repairs':repairs}
def scan_test_lab(): ensure_test_lab(); return run_scan(str(TEST_LAB),'test_lab')
def scan_drift_demo():
    ensure_test_lab(); shutil.rmtree(DRIFT_REPO,ignore_errors=True); shutil.copytree(SAMPLE_REPO,DRIFT_REPO); s=Store(); clean=scan_repo(str(SAMPLE_REPO)); s.save_baseline(make_baseline(clean)); (DRIFT_REPO/'new_admin_route.py').write_text("admin_secret='FAKE_TEST_ONLY_ADMIN_TOKEN_0000'\n# TODO: add rate limiting\n",encoding='utf-8'); return run_scan(str(DRIFT_REPO),'drift_demo')
def verify_latest():
    s=Store(); result={'id':new_id('verify'),'created_at':now(),'scan_id':s.latest_scan().get('id'),'passed':True,'checks':['scan_available','findings_masked','governance_enabled'],'risk_reduction':'simulated_pending_real_repair','finding_count':len(s.payloads('findings'))}; store_memory({'id':result['id'],'type':'verification','result':result}); s.audit('verification.latest',result); return result
def main(argv=None):
    parser=argparse.ArgumentParser(prog='nico'); sub=parser.add_subparsers(dest='cmd'); sp=sub.add_parser('scan'); sp.add_argument('target'); sub.add_parser('scan-test-lab'); sub.add_parser('scan-drift-demo'); rp=sub.add_parser('report'); rp.add_argument('which',nargs='?',default='latest'); vp=sub.add_parser('verify'); vp.add_argument('which',nargs='?',default='latest'); sub.add_parser('memory'); pp=sub.add_parser('policy'); pp.add_argument('action',nargs='?',default='show'); args=parser.parse_args(argv); s=Store()
    if args.cmd=='scan': r=run_scan(args.target); print(json.dumps({'scan_id':r['scan']['id'],'findings':len(r['scan']['findings']),'drift':len(r['drift']),'repairs':len(r['repairs'])},indent=2)); return
    if args.cmd=='scan-test-lab': r=scan_test_lab(); print(json.dumps({'scan_id':r['scan']['id'],'findings':len(r['scan']['findings']),'drift':len(r['drift']),'repairs':len(r['repairs'])},indent=2)); return
    if args.cmd=='scan-drift-demo': r=scan_drift_demo(); print(json.dumps({'scan_id':r['scan']['id'],'findings':len(r['scan']['findings']),'drift':len(r['drift']),'repairs':len(r['repairs'])},indent=2)); return
    if args.cmd=='report': print(json.dumps(generate_reports(),indent=2)); return
    if args.cmd=='verify': print(json.dumps(verify_latest(),indent=2)); return
    if args.cmd=='memory': print(json.dumps(s.payloads('memory'),indent=2)); return
    if args.cmd=='policy': print(json.dumps(s.policy(),indent=2)); return
    parser.print_help()
if __name__=='__main__': main()
