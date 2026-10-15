"""Owned Git fixtures reproduce the reported config edits without a Next build."""
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from nico.nico_ci_typescript_evidence_v1 import REPOSITORY, export_post_build


def git(root,*args):
    return subprocess.check_output(['git','-c','user.name=Owned fixture','-c','user.email=owned@example.invalid',*args],cwd=root,text=True).strip()


@pytest.fixture
def tracked_project(tmp_path):
    root=tmp_path/'owned'; root.mkdir()
    git(root,'init','-q')
    config=root/'apps/web/tsconfig.json'; config.parent.mkdir(parents=True)
    config.write_text(json.dumps({'compilerOptions':{'jsx':'preserve','strict':False,'skipLibCheck':True,'allowJs':True},
                                 'include':['next-env.d.ts','**/*.ts','**/*.tsx','.next/types/**/*.ts']}))
    git(root,'add','apps/web/tsconfig.json'); git(root,'commit','-qm','Owned configuration')
    return root,config


def export(root,out):
    calls=[]
    def runner(*args):
        calls.append(args)
        return 0,json.dumps({'schema':'nico.ci-typescript.v1','status':'completed','clean':True,'capture_complete':True}).encode(),b'',False,False
    result=export_post_build(root,out,env={'GITHUB_REPOSITORY':REPOSITORY,'GITHUB_SHA':git(root,'rev-parse','HEAD'),
                            'NICO_BUILD_OUTCOME':'success'},runner=runner)
    return result,calls


@pytest.mark.parametrize('edit',['jsx','dev_include','both'])
def test_reported_tracked_config_mutation_stops_before_compiler(tracked_project,tmp_path,edit):
    root,config=tracked_project
    original=config.read_bytes(); value=json.loads(original)
    if edit in {'jsx','both'}: value['compilerOptions']['jsx']='react-jsx'
    if edit in {'dev_include','both'}: value['include'].append('.next/dev/types/**/*.ts')
    config.write_text(json.dumps(value))
    assert git(root,'status','--porcelain','--untracked-files=no')=='M apps/web/tsconfig.json'
    out=tmp_path/'evidence'; result,calls=export(root,out)
    assert result['status']=='incomplete' and result['clean'] is False
    assert result['reason']=='tracked_source_modified'
    assert result['capture_complete'] is False and calls==[]
    assert (out/'typescript.log').read_bytes()==b''
    manifest=json.loads((out/'manifest.json').read_text())
    for name,digest in manifest['files'].items():
        assert hashlib.sha256((out/name).read_bytes()).hexdigest()==digest
    assert config.read_bytes()!=original  # The guard does not silently reset edits.


def test_explicitly_committed_configuration_keeps_guard_enabled(tracked_project,tmp_path):
    root,config=tracked_project
    value=json.loads(config.read_text())
    value['compilerOptions']['jsx']='react-jsx'; value['include'].append('.next/dev/types/**/*.ts')
    config.write_text(json.dumps(value)); git(root,'add','apps/web/tsconfig.json'); git(root,'commit','-qm','Owned explicit configuration')
    assert git(root,'status','--porcelain','--untracked-files=no')==''
    result,calls=export(root,tmp_path/'evidence')
    assert result['status']=='completed' and len(calls)==1
    assert result['source_inventory']['apps/web/tsconfig.json']==hashlib.sha256(config.read_bytes()).hexdigest()


def test_checkout_configuration_declares_next_requirements_without_weaker_checks():
    config=json.loads((Path(__file__).resolve().parents[1]/'apps/web/tsconfig.json').read_text())
    assert config['compilerOptions']['jsx']=='react-jsx'
    assert '.next/dev/types/**/*.ts' in config['include']
    assert '.next/types/**/*.ts' in config['include']
    assert config['compilerOptions']['strict'] is False
    assert config['compilerOptions']['skipLibCheck'] is True
    assert config['compilerOptions']['allowJs'] is True
    assert 'checkJs' not in config['compilerOptions']
    assert config['exclude']==['node_modules']


def test_unexpected_tracked_source_mutation_remains_rejected(tracked_project,tmp_path):
    root,_=tracked_project
    source=root/'apps/web/owned.ts'; source.write_text('export const value=1;')
    git(root,'add','apps/web/owned.ts'); git(root,'commit','-qm','Owned source')
    source.write_text('export const value=2;')
    result,calls=export(root,tmp_path/'evidence')
    assert result['reason']=='tracked_source_modified' and result['status']=='incomplete'
    assert not calls
