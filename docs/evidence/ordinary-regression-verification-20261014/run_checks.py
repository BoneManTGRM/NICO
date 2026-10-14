import json, os, signal, subprocess, time
from pathlib import Path
root=Path('/workspace/NICO'); out=Path('/workspace/nico-verification-506880a4')
python='/workspace/nico-venv/bin/python'
base='tests/test_cross_locale_pdf_repeatability_v1.py::test_same_frozen_input_keeps_cross_locale_pdf_bytes'
jobs=[]
for seed in range(1,5):
 for direction in ('en-es-MX','es-MX-en'):
  label=f'cold-seeds{seed}-{direction}'
  jobs.append((label,[python,'-m','pytest','-q',f'{base}[fresh_process-seeds{seed}-{direction}]',f'--junitxml={out / (label+".xml")}'],420))
modules=['test_comprehensive_approved_review_truth_v1','test_comprehensive_approved_lifecycle_consistency_v1','test_comprehensive_operator_presentation_v1','test_comprehensive_spanish_final_report_runtime_cache_v94','test_comprehensive_scanner_inventory_v1','test_comprehensive_same_run_locale_report_v1','test_frozen_source_pdf_readonly_work_v1','test_spanish_absent_literal_fast_path','test_spanish_presentation_parity_v1','test_spanish_canonical_report_parity_v87','test_spanish_canonical_evidence_literals_v95','test_scanner_status_record_retention','test_review_pdf_download_incident','test_retained_pdf_exact_input_cache_v1','test_cross_locale_pdf_repeatability_v1']
jobs.append(('ordinary-python',[python,'-m','pytest','-q',*[f'tests/{x}.py' for x in modules],'-k','not fresh_process',f'--junitxml={out / "ordinary-python.xml"}','--durations=10'],900))
jobs.append(('ordinary-javascript',['node','--test','tests/js/assessment-poll-exhaustion.test.cjs','tests/js/review-pdf-download.test.cjs','tests/js/pdf-proxy-stream-diagnostics.test.cjs','tests/js/workspace-review-pdf-fallback.test.cjs'],120))
jobs.append(('typescript',['npm','--prefix','apps/web','run','lint'],120))
manifest={'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'jobs':[{'name':n,'command':c,'outer_timeout_seconds':t,'status':'not_started'} for n,c,t in jobs]}
def save():
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
save()
for entry,(_,cmd,limit) in zip(manifest['jobs'],jobs):
 start=time.monotonic();entry['status']='running';save();print('START '+entry['name'],flush=True)
 with (out/(entry['name']+'.txt')).open('w') as log:
  p=subprocess.Popen(cmd,cwd=root,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  try:
   entry['exit_code']=p.wait(timeout=limit);entry['status']='passed' if entry['exit_code']==0 else 'failed'
  except subprocess.TimeoutExpired:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
   entry['status']='timed_out';entry['exit_code']=p.returncode
 entry['elapsed_seconds']=round(time.monotonic()-start,3);save();print('END '+entry['name']+' '+entry['status'],flush=True)
