"""Hosted-only synthetic reviewer proof against an already built Next application.

Never targets a deployment: fixed loopback server, synthetic cookie, intercepted
review reads, every other API/write/external request blocked. Not an auth test.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import time
import threading
import shutil
import re
from reviewer_proof_environment import environment
from reviewer_proof_diagnostics import RESERVED_BYTES, run_with_diagnostics, set_stage
from urllib.parse import urlsplit

ORIGIN = 'http://127.0.0.1:3107'
RUN = 'comprun_synthetic_visual'
API = f'/api/nico/assessment/comprehensive-run/{RUN}/review-work'
SCENARIOS = ('qualified', 'unqualified', 'duplicate', 'stale', 'dependency')
VIEWPORTS = {'desktop': (1280, 1000), 'mobile': (390, 844)}


def request_kind(method, url):
    parsed = urlsplit(url)
    if method != 'GET' or f'{parsed.scheme}://{parsed.netloc}' != ORIGIN:
        return 'blocked'
    if parsed.path == API and not parsed.query:
        return 'synthetic'
    if parsed.path == '/operations/reviewer-queue' or parsed.path.startswith('/_next/static/'):
        return 'asset'
    if parsed.path == '/favicon.ico':
        return 'empty'
    return 'blocked'


def fixture(sha, scenario):
    assert scenario in SCENARIOS
    if scenario == 'dependency':
        return dependency_fixture(sha)
    row = {'candidate_id':'synthetic-candidate','record_index':0,
           'recommendation':'resolve_evidence_gaps','limitations':['unresolved_proof_gaps'],
           'source_url':None,'input_sha256':'a'*64,'existing_review_profile_cluster_id':'synthetic'}
    source = {'candidate_id':row['candidate_id'],'record_index':0,'candidate_input_sha256':'b'*64,
              'rule_id':'B603','completed':True,'source_sha256':'c'*64,'source_path':'synthetic/app.py',
              'line':2,'reason':'exact_line_structure_only','lexical_binding':{
                  'version':'nico.reviewer-lexical-binding.v1','api':'subprocess.run',
                  'import_line':1,'line':2,'source_sha256':'c'*64}}
    queue = [row]
    if scenario == 'unqualified':
        source.pop('lexical_binding')
    if scenario == 'duplicate':
        queue.append({**row,'record_index':1,'input_sha256':'d'*64})
    if scenario == 'stale':
        source['lexical_binding']['version'] = 'stale'
    return {'run_id':RUN,'repository':'synthetic/reviewer','commit_sha':sha,'evidence_ledger_id':'synthetic-ledger',
            'candidate_count':len(queue),'dispositioned_candidate_count':0,'remaining_candidate_count':len(queue),
            'quality_control_required_count':len(queue),'quality_control_completed_count':0,'open_evidence_request_count':0,
            'candidates':[{'candidate_id':q['candidate_id']} for q in queue],'clusters':[],
            'ledger':{'audit_events':[],'quality_control':{},'evidence_requests':[]},
            'queue_counts':{},'workload_metrics':{},'quality_control_sampling':{},'empirical_measurement':{},
            'human_review_required':True,'client_delivery_allowed':False,'ready_for_final_approval':False,
            'unresolved_high_impact_candidate_ids':[],'quality_control_blockers':{},
            'review_assistance':{'artifact_schema':'nico.candidate-review-assistance.v1',
                'pending_record_count':len(queue),'queue':queue,
                'source_investigation':{'available':True,'candidate_count':len(queue),'completed_count':1,'packets':[source]}}}


DEPENDENCY_CASES = ('qualified', 'stale', 'duplicate', 'missing', 'foreign', 'wrong-index',
    'unknown', 'collected-without-receipt', 'supply_scanner_identity', 'supply_current_capture',
    'supply_lockfile_observation', 'inspect_lockfile_capture', 'reconcile_lockfile_identity')
DEPENDENCY_PACKAGE = '@synthetic/' + 'long-package-name-' * 6
DEPENDENCY_PATH = 'synthetic/' + 'nested-directory/' * 8 + 'package-lock.json'


def dependency_fixture(sha):
    payload = fixture(sha, 'qualified')
    queue, packets = [], []
    for index, case in enumerate(DEPENDENCY_CASES):
        row = deepcopy(payload['review_assistance']['queue'][0])
        row.update(candidate_id='dependency-' + case, record_index=index,
            source_record_index=index + 20, source_candidate_input_sha256='b'*64,
            evidence_tasks=['identify_package', 'identify_locked_version', 'verify_affectedness', 'verify_runtime_use'])
        source = dict(candidate_id=row['candidate_id'], record_index=index + 20,
            candidate_input_sha256='b'*64, completed=False, rule_id='SYNTHETIC-DEPENDENCY',
            reason='unsupported_or_missing_exact_source_evidence', dependency_next_step='verify_installation_and_use')
        if case in ('qualified', 'stale', 'duplicate', 'foreign', 'wrong-index'):
            source['dependency_identity'] = dict(package=DEPENDENCY_PACKAGE, locked_version='1.2.3-synthetic',
                lockfile_path=DEPENDENCY_PATH, source_sha256='c'*64)
        if case == 'stale': source['candidate_input_sha256'] = 'd'*64
        if case == 'foreign': source['candidate_id'] = 'unrelated-source'
        if case == 'wrong-index': source['record_index'] = -1
        if case == 'unknown': source['dependency_next_step'] = 'PRIVATE_UNTRUSTED_GUIDANCE'
        if case.startswith(('supply_', 'inspect_', 'reconcile_')): source['dependency_next_step'] = case
        if case != 'missing': packets.append(source)
        if case == 'duplicate': packets.append(deepcopy(source))
        queue.append(row)
    for key in ('candidate_count', 'remaining_candidate_count', 'quality_control_required_count'):
        payload[key] = len(queue)
    payload['candidates'] = [{'candidate_id':row['candidate_id']} for row in queue]
    payload['review_assistance'].update(queue=queue, pending_record_count=len(queue),
        source_investigation={'available':True, 'candidate_count':len(queue), 'completed_count':0, 'packets':packets})
    return payload


def validate_dependency_text(case, locale, text, guidance_count):
    """Shared assertions exercise actual rendered text, never fixture truth alone."""
    es = locale == 'es-MX'
    qualified = case == 'qualified'
    assert ('1.2.3-synthetic' in text) == qualified
    assert (DEPENDENCY_PACKAGE in text) == qualified
    assert (DEPENDENCY_PATH in text) == qualified
    assert ('Identificar el paquete en' if es else 'Identify the package in') in text or qualified
    assert ('afectación sigue sin resolverse' if es else 'affectedness remains unresolved') in text
    assert ('Mantener el candidato pendiente' if es else 'Keep the candidate pending') in text
    assert 'PRIVATE_UNTRUSTED_GUIDANCE' not in text
    expected_guidance = qualified or case.startswith(('supply_', 'inspect_', 'reconcile_'))
    assert guidance_count == int(expected_guidance)
    if qualified:
        assert ('no confirma instalación ni seguridad' if es else 'not proof of installation or safety') in text
        assert ('Identificar el paquete en' if es else 'Identify the package in') not in text
    guidance_labels = {
        'supply_scanner_identity': ('First obtain the scanner', 'Primero obtener el nombre del paquete'),
        'supply_current_capture': ('First obtain retained source evidence', 'Primero obtener evidencia conservada'),
        'supply_lockfile_observation': ('First obtain an observation', 'Primero obtener una observación'),
        'inspect_lockfile_capture': ('First inspect the retained capture outcome', 'Primero revisar el resultado conservado'),
        'reconcile_lockfile_identity': ('First reconcile the scanner claim', 'Primero conciliar la afirmación'),
    }
    if case in guidance_labels:
        assert guidance_labels[case][int(es)] in text
    if case == 'supply_lockfile_observation':
        assert ('causa se desconoce' if es else 'cause is unknown') in text
    if case == 'reconcile_lockfile_identity':
        assert ('no suponer que se intentó la coincidencia' if es else 'do not assume that matching was attempted') in text


def validate_styles(styles, responses, computed):
    assert styles, 'no application stylesheet'
    for item in styles:
        assert request_kind('GET', item['href']) == 'asset' and '/_next/static/' in item['href']
        assert responses.get(item['href']) == 200, 'stylesheet response failed or absent'
        assert item['rules'] > 0, 'stylesheet missing or empty CSSOM'
    assert computed['bodyMargin'] == '0px' and computed['boxSizing'] == 'border-box', 'production CSS not applied'


TOTAL_ARTIFACT_BYTES = 20 * 1024 * 1024 - RESERVED_BYTES


def finalize_artifacts(raw, publish, manifest):
    """Only finalized bytes are uploadable; over-budget failure emits no artifact."""
    (raw/'manifest.json').write_text(json.dumps(manifest,indent=2))
    files=list(raw.iterdir())
    if any(not f.is_file() or f.is_symlink() for f in files):
        raise RuntimeError('unexpected proof artifact')
    if sum(f.stat().st_size for f in files)>TOTAL_ARTIFACT_BYTES:
        raise RuntimeError('final artifact total exceeds cap; upload directory not created')
    shutil.copytree(raw,publish)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--expected-sha',required=True)
    parser.add_argument('--reviewed-head',required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    assert sha == args.expected_sha, 'checkout identity mismatch'
    assert re.fullmatch('[0-9a-f]{40}',args.reviewed_head)
    parents=[line.split()[1] for line in subprocess.check_output(['git','cat-file','-p','HEAD'],cwd=root,text=True).splitlines() if line.startswith('parent ')]
    assert args.reviewed_head == sha or args.reviewed_head in parents, 'reviewed head is not checkout or merge parent'
    args.output.mkdir(parents=True,exist_ok=False)
    raw=args.output/'raw';raw.mkdir()
    manifest={'schema':'nico.reviewer-binding-webkit-proof.v1','checkout_sha':sha,'reviewed_head_sha':args.reviewed_head,'tree_sha':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=root,text=True).strip(),'cases':[],
              'synthetic_only':True,'authentication_verified':False,'production_deployment_verified':False}
    set_stage('playwright-import')
    from playwright.sync_api import sync_playwright
    start=time.monotonic()
    with (raw/'server.log').open('wb') as log:
        set_stage('server-start')
        server=subprocess.Popen(['node','node_modules/next/dist/bin/next','start','-H','127.0.0.1','-p','3107'],
            cwd=root/'apps/web',env=environment(root,'server'),stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        def drain():
            remaining=256*1024
            while data:=server.stdout.read(8192):
                log.write(data[:remaining]);remaining=max(0,remaining-len(data))
        reader=threading.Thread(target=drain,daemon=True);reader.start()
        try:
            set_stage('browser-proof')
            with sync_playwright() as p:
                browser=p.webkit.launch()  # normal installed runner; no sandbox overrides
                for locale in ('en','es-MX'):
                    for viewport,(width,height) in VIEWPORTS.items():
                        for scenario in SCENARIOS:
                            assert time.monotonic()-start < 180, 'browser proof budget exhausted'
                            context=browser.new_context(viewport={'width':width,'height':height},locale=locale,service_workers='block')
                            # Only the isolated local server sees this generated marker. No real auth API is called.
                            context.add_cookies([{'name':'nico-specialist-session','value':'synthetic-render-only','url':ORIGIN}])
                            payload=fixture(sha,scenario); requests=[]; errors=[]; css_responses={}
                            def route_request(route):
                                req=route.request;kind=request_kind(req.method,req.url)
                                requests.append({'method':req.method,'url':req.url,'decision':kind})
                                if kind=='synthetic':route.fulfill(json=deepcopy(payload))
                                elif kind=='asset':route.continue_()
                                elif kind=='empty':route.fulfill(status=204,body='')
                                else:route.abort('blockedbyclient')
                            context.route('**/*',route_request)
                            page=context.new_page();page.on('pageerror',lambda e: errors.append(str(e)))
                            page.on('response',lambda response: css_responses.__setitem__(response.url,response.status) if response.request.resource_type=='stylesheet' else None)
                            page.set_default_timeout(10000)
                            # Bounded readiness retries only against this owned loopback server.
                            for attempt in range(20):
                                try:
                                    page.goto(f'{ORIGIN}/operations/reviewer-queue?run_id={RUN}&lang={locale}',wait_until='domcontentloaded',timeout=3000)
                                    break
                                except Exception:
                                    if attempt==19 or server.poll() is not None:raise
                                    time.sleep(.25)
                            page.get_by_role('button',name='Load review work' if locale=='en' else 'Cargar trabajo de revisión',exact=True).click()
                            page.evaluate('document.fonts.ready')
                            section=page.get_by_role('region',name='Review assistance' if locale=='en' else 'Asistencia para revisión')
                            section.wait_for(state='visible')
                            details=section.locator('details')
                            assert details.count()==len(payload['review_assistance']['queue'])
                            for detail in details.all():detail.locator('summary').click()
                            proof=section.locator('[data-lexical-binding="true"]')
                            assert proof.count()==(1 if scenario=='qualified' else 0)
                            if scenario=='qualified':
                                assert proof.is_visible() and 'subprocess.run' in proof.inner_text()
                                assert ('runtime dispatch' if locale=='en' else 'despacho en ejecución') in section.inner_text()
                            if scenario == 'dependency':
                                for case in DEPENDENCY_CASES:
                                    detail = section.locator('[data-review-assistance-candidate="dependency-' + case + '"]')
                                    assert detail.locator('[data-dependency-evidence="true"]').count() == 1
                                    validate_dependency_text(case, locale, detail.inner_text(), detail.locator('[data-dependency-next-step="true"]').count())
                            assert ('Every disposition remains human' if locale=='en' else 'Cada disposición sigue siendo humana') in section.inner_text()
                            assert payload['human_review_required'] and not payload['client_delivery_allowed'] and not payload['ready_for_final_approval']
                            # Require real loaded production styles, not a fixture stylesheet.
                            styles=page.locator('link[rel="stylesheet"]').evaluate_all('els => els.map(e => ({href:e.href,rules:e.sheet ? e.sheet.cssRules.length : 0}))')
                            computed=section.evaluate('el => ({bodyMargin:getComputedStyle(document.body).margin,boxSizing:getComputedStyle(el).boxSizing})')
                            validate_styles(styles,css_responses,computed)
                            geometry=section.evaluate('''el => {const r=el.getBoundingClientRect();return {width:r.width,left:r.left,right:r.right,viewport:innerWidth,scroll:el.scrollWidth,client:el.clientWidth};}''')
                            assert geometry['width']>0 and geometry['left']>=-1 and geometry['right']<=width+1,geometry
                            assert geometry['scroll']<=geometry['client']+1,geometry
                            for node in section.locator('p, summary, code, [data-dependency-evidence] li').all():
                                if node.is_visible():
                                    box=node.bounding_box();assert box and box['width']>0 and box['x']>=-1 and box['x']+box['width']<=width+1,box
                            assert not errors,errors
                            assert not [r for r in requests if r['method']!='GET'],requests
                            assert any(r['decision']=='synthetic' for r in requests)
                            rects=section.locator('p, summary').evaluate_all('els => els.filter(e => e.getClientRects().length).map(e => {const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height};})')
                            for i,a in enumerate(rects):
                                for b in rects[i+1:]:
                                    assert not (min(a['x']+a['w'],b['x']+b['w'])-max(a['x'],b['x'])>1 and min(a['y']+a['h'],b['y']+b['h'])-max(a['y'],b['y'])>1), 'overlapping text blocks'
                            name=f'{locale}-{viewport}-{scenario}'
                            image=raw/(name+'.png');pixels=section.screenshot()
                            assert sum(f.stat().st_size for f in raw.iterdir() if f.is_file())+len(pixels) <= 20*1024*1024, 'artifact budget exhausted'
                            image.write_bytes(pixels)
                            manifest['cases'].append({'name':name,'geometry':geometry,'requests':requests,'styles':styles,'stylesheet_responses':css_responses,'computed_style':computed,
                                'payload_sha256':hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),
                                'screenshot':image.name,'screenshot_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'status':'passed'})
                            assert sum(f.stat().st_size for f in raw.iterdir() if f.is_file()) <= 20*1024*1024, 'artifact budget exhausted'
                            context.close()
                browser.close()
        finally:
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()
            reader.join(timeout=5);assert not reader.is_alive(), 'server log drain incomplete'
            log.flush()
            manifest['elapsed_seconds']=time.monotonic()-start
            manifest['complete']=len(manifest['cases'])==len(SCENARIOS)*len(VIEWPORTS)*2
            finalize_artifacts(raw,args.output/'publish',manifest)
    assert manifest['complete']

if __name__=='__main__':
    run_with_diagnostics(Path(__file__).resolve().parents[1], 'proof', main)
