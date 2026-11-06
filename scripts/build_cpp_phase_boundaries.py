"""Build/capture a diagnostic-only image derived from the exact production image."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from uuid import uuid4
from . import cpp_phase_boundaries as phase

UPSTREAM='ac9db3069b9f90e81e126a090b99ad456e122cf8'
AFTER='5032dbae909f6eb3b06e94511b9e5c0cc84b8c5c64b1cd985c39336dc2f5eec7'
BINARY='/usr/local/bin/cppcheck-phase-boundaries'
FILES={'production_binary':'/usr/local/bin/cppcheck',
       'clang_observer':'/opt/nico-clang-header-observer.so',
       'repair_receipt':'/opt/nico-cppcheck-repair.json',
       'grammar_receipt':'/opt/nico-cppcheck-header-grammar.json',
       'header_receipt':'/opt/nico-cppcheck-header-observer.json',
       'clang_receipt':'/opt/nico-clang-header-observer.json'}

def digest(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def image_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'sha256:[a-f0-9]{64}',value):raise ValueError('phase_image_identity')
    return value

def recipe(original):
    image_id(original)
    return f'''# Original image identity: {original}
FROM nico-phase-base:{original[7:]}
USER 0:0
COPY cppcheck /opt/phase-tool-src
COPY repair_cppcheck_placement_ast.py repair_cppcheck_header_grammar.py patch_cppcheck_header_evidence.py cpp_phase_boundaries.py /opt/
COPY cppcheck-header-evidence /opt/cppcheck-header-evidence
RUN test "$(g++ -dumpfullversion)" = 14.2.0 \\
 && python3 /opt/repair_cppcheck_placement_ast.py /opt/phase-tool-src/lib/tokenlist.cpp > /opt/phase-repair.json \\
 && cmp /opt/phase-repair.json /opt/nico-cppcheck-repair.json \\
 && python3 /opt/repair_cppcheck_header_grammar.py /opt/phase-tool-src > /opt/phase-grammar.json \\
 && cmp /opt/phase-grammar.json /opt/nico-cppcheck-header-grammar.json \\
 && python3 /opt/patch_cppcheck_header_evidence.py /opt/phase-tool-src /opt/cppcheck-header-evidence > /opt/phase-header.json \\
 && cmp /opt/phase-header.json /opt/nico-cppcheck-header-observer.json \\
 && python3 /opt/cpp_phase_boundaries.py --source /opt/phase-tool-src > /opt/nico-phase-overlay.json \\
 && timeout 180s make -C /opt/phase-tool-src -j2 MATCHCOMPILER=yes FILESDIR=/opt/cppcheck 'CXXFLAGS=-O2 -DNDEBUG' \\
 && cp /opt/phase-tool-src/cppcheck {BINARY} \\
 && rm -rf /opt/phase-tool-src
USER 1000:1000
'''

def expected_overlay():
    return {'schema':'nico.cpp-phase-overlay.v1','source_sha256':phase.PIN,
        'instrumented_source_sha256':AFTER,'restored_source_sha256':phase.PIN,
        'script_sha256':digest(Path(phase.__file__).read_bytes()),
        'instrumentation_only':True,'qualification_credit':False}

def prepare(context,source,original):
    if context.exists() or context.is_symlink():raise ValueError('phase_context_not_fresh')
    head=subprocess.run(['git','-C',str(source),'rev-parse','HEAD'],check=True,capture_output=True,timeout=15).stdout.decode().strip()
    dirty=subprocess.run(['git','-C',str(source),'status','--porcelain','--untracked-files=all'],check=True,capture_output=True,timeout=15).stdout
    if head!=UPSTREAM or dirty:raise ValueError('phase_upstream_identity')
    # BuildKit accepts a local tag, not a bare image ID in FROM. Bind the tag
    # to the verified ID; never request a registry image or a mutable remote tag.
    tag='nico-phase-base:'+image_id(original)[7:]
    subprocess.run(['docker','tag',original,tag],check=True,capture_output=True,timeout=15)
    metadata=json.loads(subprocess.run(['docker','image','inspect',tag],check=True,capture_output=True,timeout=15).stdout)
    if len(metadata)!=1 or metadata[0].get('Id')!=original:raise ValueError('phase_base_tag_identity')
    context.mkdir()
    shutil.copytree(source,context/'cppcheck',ignore=shutil.ignore_patterns('.git'))
    scripts=Path(__file__).resolve().parent
    for name in ('repair_cppcheck_placement_ast.py','repair_cppcheck_header_grammar.py','patch_cppcheck_header_evidence.py','cpp_phase_boundaries.py'):
        shutil.copyfile(scripts/name,context/name)
    shutil.copytree(scripts/'cppcheck-header-evidence',context/'cppcheck-header-evidence')
    (context/'Dockerfile').write_text(recipe(original))
    return {'recipe_sha256':digest(recipe(original).encode()),'upstream':UPSTREAM}

def capture_files(image,paths,output):
    image_id(image);name='nico-phase-'+uuid4().hex;owner=uuid4().hex
    from .native_stage_counters.build import cleanup_capture_container
    try:
        subprocess.run(['docker','create','--name',name,'--label','nico.stage.capture-owner='+owner,
            '--network=none','--read-only','--entrypoint=/bin/true',image],check=True,capture_output=True,timeout=15)
        found={}
        for key,path in paths.items():
            target=output/key
            subprocess.run(['docker','cp',name+':'+path,str(target)],check=True,capture_output=True,timeout=15)
            if target.is_symlink() or not target.is_file() or target.stat().st_size>64*1024*1024:
                raise ValueError('phase_capture_file')
            found[key]=target.read_bytes()
        return found
    finally:cleanup_capture_container(name,owner)

def validate_binding(value,image):
    keys={'schema','original_image','image','upstream','recipe_sha256','overlay','files','diagnostic_binary_sha256','diagnostic_binary_path','qualification_credit'}
    if not isinstance(value,dict) or set(value)!=keys:raise ValueError('phase_binding_shape')
    original=image_id(value['original_image']);image_id(image)
    if (value['schema']!='nico.cpp-phase-binding.v1' or value['image']!=image or image==original
        or value['upstream']!=UPSTREAM or value['recipe_sha256']!=digest(recipe(original).encode())
        or canonical(value['overlay'])!=canonical(expected_overlay()) or value['diagnostic_binary_path']!=BINARY
        or value['qualification_credit'] is not False or not isinstance(value['files'],dict)
        or set(value['files'])!=set(FILES)):raise ValueError('phase_binding_identity')
    for sha in [*value['files'].values(),value['diagnostic_binary_sha256']]:
        if not isinstance(sha,str) or not re.fullmatch(r'[a-f0-9]{64}',sha):raise ValueError('phase_binding_hash')
    if value['diagnostic_binary_sha256']==value['files']['production_binary']:raise ValueError('phase_binary_unchanged')
    return value

def capture(original,image,output,recipe_path):
    if recipe_path.read_bytes()!=recipe(original).encode():raise ValueError('phase_recipe_mismatch')
    layers=[]
    for identity in (original,image):
        image_id(identity)
        result=subprocess.run(['docker','image','inspect',identity],check=True,capture_output=True,timeout=15)
        metadata=json.loads(result.stdout)
        if len(metadata)!=1 or metadata[0].get('Id')!=identity:raise ValueError('phase_image_inspect')
        values=metadata[0].get('RootFS',{}).get('Layers')
        if not isinstance(values,list) or not values or any(not isinstance(v,str) or not re.fullmatch('sha256:[a-f0-9]{64}',v) for v in values):raise ValueError('phase_image_layers')
        layers.append(values)
    if len(layers[1])<=len(layers[0]) or layers[1][:len(layers[0])]!=layers[0]:raise ValueError('phase_image_not_derived')
    if output.exists() or output.is_symlink():raise ValueError('phase_capture_not_fresh')
    output.mkdir();(output/'original').mkdir();(output/'diagnostic').mkdir()
    before=capture_files(original,FILES,output/'original')
    after=capture_files(image,{**FILES,'diagnostic_binary':BINARY,'overlay':'/opt/nico-phase-overlay.json'},output/'diagnostic')
    if any(before[k]!=after[k] for k in FILES):raise ValueError('phase_production_tool_changed')
    if canonical(json.loads(after['overlay']))!=canonical(expected_overlay()):raise ValueError('phase_overlay_identity')
    binding={'schema':'nico.cpp-phase-binding.v1','original_image':original,'image':image,'upstream':UPSTREAM,
        'recipe_sha256':digest(recipe(original).encode()),'overlay':expected_overlay(),
        'files':{k:digest(before[k]) for k in FILES},'diagnostic_binary_sha256':digest(after['diagnostic_binary']),
        'diagnostic_binary_path':BINARY,'qualification_credit':False}
    validate_binding(binding,image)
    (output/'binding.json').write_bytes(canonical(binding)+b'\n')
    return binding

def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('prepare');a.add_argument('--context',type=Path,required=True);a.add_argument('--source',type=Path,required=True);a.add_argument('--original-image',required=True)
    a=s.add_parser('capture');a.add_argument('--original-image',required=True);a.add_argument('--image',required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--recipe',type=Path,required=True)
    a=p.parse_args();r=prepare(a.context,a.source,a.original_image) if a.action=='prepare' else capture(a.original_image,a.image,a.output,a.recipe)
    print(json.dumps(r,sort_keys=True))
if __name__=='__main__':main()
