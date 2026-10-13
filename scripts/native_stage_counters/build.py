"""Prepare a private diagnostic recipe and bind its separately built image.

No production Dockerfile is written. CLI actions run only when explicitly invoked.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4
from . import instrument
from .binding import (ARCHIVE_SHA256, BUILD_FLAGS, FLAGS, HEADER_SHA256,
                      OBSERVER_SHA256, ORIGINAL_BINARY_SHA256, validate_overlay, validate_binding)


def digest(raw): return hashlib.sha256(raw).hexdigest()


def recipe_identity(recipe):
    raw = recipe.read_text()
    copy_anchor = 'COPY verify_cpp_runtime_toolchain.py /opt/verify_cpp_runtime_toolchain.py\n'
    build_anchor = "    && timeout 180s make -C /opt/tool-src -j2 MATCHCOMPILER=yes FILESDIR=/opt/cppcheck 'CXXFLAGS=-O2 -DNDEBUG' \\\n"
    if raw.count(copy_anchor) != 1 or raw.count(build_anchor) != 1:
        raise ValueError('diagnostic_stage_recipe_anchor')
    if digest(instrument.HEADER.read_bytes()) != HEADER_SHA256:
        raise ValueError('diagnostic_stage_header_identity')
    additions = ('COPY native-stage/instrument.py /opt/nico-stage-instrument.py\n'
                 'COPY native-stage/nico_stage_counters.h /opt/nico_stage_counters.h\n')
    commands = ("    && test \"$(g++ -dumpfullversion)\" = 14.2.0 \\\n"
                '    && python3 /opt/nico-stage-instrument.py --source /opt/tool-src --output /opt/nico-stage-overlay \\\n'
                '    && cp /opt/nico-stage-overlay/lib/* /opt/tool-src/lib/ \\\n')
    updated = raw.replace(copy_anchor, copy_anchor+additions).replace(build_anchor, commands+build_anchor)
    receipt={'production_recipe_sha256':digest(raw.encode()),'diagnostic_recipe_sha256':digest(updated.encode()),
             'instrument_script_sha256':digest(Path(instrument.__file__).read_bytes()),'header_sha256':HEADER_SHA256}
    return updated, receipt


def prepare(context, recipe, destination):
    updated, receipt = recipe_identity(recipe)
    target=context/'native-stage'; target.mkdir()
    shutil.copyfile(Path(instrument.__file__),target/'instrument.py')
    shutil.copyfile(instrument.HEADER,target/'nico_stage_counters.h')
    with destination.open('x') as f: f.write(updated)
    destination.with_suffix('.receipt.json').write_text(json.dumps(receipt,sort_keys=True)+'\n')
    return receipt


def cleanup_capture_container(name, owner):
    """Resolve the invocation's label before removing its exact container ID."""
    inspected = subprocess.run(
        ['docker', 'inspect', '--type=container', '--format={{json .}}', name],
        check=False, capture_output=True, timeout=15)
    if inspected.returncode:
        # A failed create may have left no container. Other daemon failures are
        # not evidence of absence and must remain visible.
        missing = {f'Error: No such object: {name}', f'Error: No such container: {name}'}
        if inspected.stderr.decode(errors='replace').strip() in missing:
            return
        raise subprocess.CalledProcessError(inspected.returncode, inspected.args,
                                            inspected.stdout, inspected.stderr)
    value = json.loads(inspected.stdout)
    container_id = value.get('Id', '')
    if (value.get('Name') != '/' + name
            or value.get('Config', {}).get('Labels', {}).get('nico.stage.capture-owner') != owner
            or not re.fullmatch(r'[a-f0-9]{64}', container_id)):
        raise ValueError('diagnostic_stage_cleanup_ownership_mismatch')
    subprocess.run(['docker', 'rm', '--force', container_id],
                   check=True, capture_output=True, timeout=15)


def capture(original_image, image, output, recipe):
    """Read tool bytes from stopped containers, never execute their entrypoints."""
    output.mkdir()
    hashes={}; overlay=None
    for kind,identity in [('original',original_image),('instrumented',image)]:
        if not __import__('re').fullmatch(r'sha256:[a-f0-9]{64}',identity):
            raise ValueError('diagnostic_stage_image_invalid')
        name='nico-stage-bind-'+uuid4().hex
        owner=uuid4().hex
        failure=None
        try:
            subprocess.run(['docker','create','--name',name,'--label','nico.stage.capture-owner='+owner,
                            '--network=none','--read-only','--entrypoint=/bin/true',identity],
                           check=True,capture_output=True,timeout=15)
            for key,path in [('binary','/usr/local/bin/cppcheck'),('observer','/opt/nico-clang-header-observer.so')]:
                target=output/(kind+'-'+key)
                subprocess.run(['docker','cp',name+':'+path,str(target)],check=True,capture_output=True,timeout=15)
                hashes[kind+'-'+key]=digest(target.read_bytes())
            if kind=='instrumented':
                target=output/'overlay.json'
                subprocess.run(['docker','cp',name+':/opt/nico-stage-overlay/stage-counter-receipt.json',str(target)],check=True,capture_output=True,timeout=15)
                overlay=validate_overlay(json.loads(target.read_text()))
        except BaseException as exc:
            failure=exc
            raise
        finally:
            try:
                cleanup_capture_container(name, owner)
            except Exception as cleanup_error:
                if failure is None:
                    raise
                failure.add_note('diagnostic_stage_cleanup_failed: '
                                 + type(cleanup_error).__name__ + ': ' + str(cleanup_error))
    if hashes['original-binary'] != ORIGINAL_BINARY_SHA256 or any(hashes[k+'-observer']!=OBSERVER_SHA256 for k in ('original','instrumented')):
        raise ValueError('diagnostic_stage_original_tool_identity')
    # Recipe identity is re-derived independently from the reviewed production file.
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as temp:
        expected=prepare(Path(temp),Path('docker/assessment-full-project-fuzz.Dockerfile'),Path(temp)/'Dockerfile')
    if digest(recipe.read_bytes())!=expected['diagnostic_recipe_sha256']:
        raise ValueError('diagnostic_stage_recipe_identity')
    binding={'schema':'nico.stage-runtime-binding.v1','original_image':original_image,'image':image,
             'original_binary_sha256':ORIGINAL_BINARY_SHA256,'instrumented_binary_sha256':hashes['instrumented-binary'],
             'observer_sha256':OBSERVER_SHA256,'original_archive_sha256':ARCHIVE_SHA256,
             'flags':FLAGS,'build_flags':BUILD_FLAGS,'compiler_version':'14.2.0',
             'activation':{'environment':'NICO_CPP_STAGE_COUNTERS','exact_value':'1'},
             'build_verified':True,'overlay':overlay,'recipe':expected}
    from .binding import binding_digest
    bound_sha = binding_digest(binding)
    validate_binding(binding,image,bound_sha,original_image)
    (output/'binding.json').write_text(json.dumps(binding,sort_keys=True)+'\n')
    (output/'binding.sha256').write_text(bound_sha+'\n')
    return binding


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('prepare');a.add_argument('--context',type=Path,required=True);a.add_argument('--recipe',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('capture');a.add_argument('--original-image',required=True);a.add_argument('--image',required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--recipe',type=Path,required=True)
    args=p.parse_args()
    result=prepare(args.context,args.recipe,args.output) if args.action=='prepare' else capture(args.original_image,args.image,args.output,args.recipe)
    print(json.dumps(result,sort_keys=True))
if __name__=='__main__':main()
