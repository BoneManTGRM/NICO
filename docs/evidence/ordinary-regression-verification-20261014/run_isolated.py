import json, os, signal, subprocess, time
from pathlib import Path
root=Path('/workspace/NICO'); out=Path('/workspace/nico-verification-506880a4'); python='/workspace/nico-venv/bin/python'
prior=json.loads((out/'manifest.json').read_text())
command=next(j['command'] for j in prior['jobs'] if j['name']=='ordinary-python')
modules=[arg for arg in command if arg.startswith('tests/')]
manifest={'base_commit':prior['commit'],'source_diff':subprocess.check_output(['git','diff','--stat'],cwd=root,text=True),'model':'one isolated pytest process per file, matching NICO CI','jobs':[{'module':m,'status':'not_started'} for m in modules]}
def save():(out/'isolated-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
save()
for entry in manifest['jobs']:
 name=Path(entry['module']).stem;entry['status']='running';save();start=time.monotonic();print('START '+name,flush=True)
 with (out/(name+'.txt')).open('w') as log:
  p=subprocess.Popen([python,'-m','pytest','-q',entry['module'],'-k','not fresh_process',f'--junitxml={out/(name+".xml")}'],cwd=root,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  try:
   entry['exit_code']=p.wait(timeout=420);entry['status']='passed' if entry['exit_code']==0 else 'failed'
  except subprocess.TimeoutExpired:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
   entry['status']='timed_out';entry['exit_code']=p.returncode
 entry['elapsed_seconds']=round(time.monotonic()-start,3);save();print('END '+name+' '+entry['status'],flush=True)
