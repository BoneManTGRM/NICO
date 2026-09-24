"""Release-owned generic selection for the configure-first C/C++ child.

Public assessment payloads cannot choose this profile. Selection requires an
exact attached GitHub snapshot, complete tree inventory, generic C/C++ + root
CMake evidence, anonymous public source access, a release-bound enablement, and
the exact qualified worker image config ID supplied by deployment settings.
"""
from __future__ import annotations
import os
import re

from nico.assessment_cpp_configure_first_contract import PROFILE

_SOURCE_SUFFIXES=('.c','.cc','.cpp','.cxx')


def _settings(environ, release_revision):
    enabled=environ.get('NICO_CPP_CONFIGURE_FIRST_ENABLED')=='1'
    dispatch=environ.get('NICO_ASSESSMENT_WORKER_DISPATCH_ENABLED')=='1'
    image=environ.get('NICO_CPP_CONFIGURE_FIRST_IMAGE_CONFIG_ID','')
    qualified=environ.get('NICO_CPP_CONFIGURE_FIRST_QUALIFIED_RELEASE','')
    run_id=environ.get('NICO_CPP_CONFIGURE_FIRST_QUALIFICATION_RUN_ID','')
    artifact=environ.get('NICO_CPP_CONFIGURE_FIRST_QUALIFICATION_ARTIFACT_SHA256','')
    if (not enabled or not dispatch
            or re.fullmatch(r'sha256:[0-9a-f]{64}',image) is None
            or re.fullmatch(r'[0-9a-f]{40}',qualified) is None
            or qualified != release_revision
            or re.fullmatch(r'[1-9][0-9]{0,19}',run_id) is None
            or re.fullmatch(r'[0-9a-f]{64}',artifact) is None):
        return None
    return {'image_config_id':image,'qualification_run_id':int(run_id),
            'qualification_artifact_sha256':artifact}


def select_configure_first_contract(repo_step, *, environ=None, release_revision=None):
    if not isinstance(repo_step,dict) or repo_step.get('status')!='complete':
        return None
    snapshot=repo_step.get('repository_snapshot')
    evidence=repo_step.get('repository_evidence')
    if not isinstance(snapshot,dict) or not isinstance(evidence,dict):
        return None
    if (snapshot.get('status')!='attached' or snapshot.get('exact_commit_verified') is not True
            or snapshot.get('provider')!='github'
            or snapshot.get('access_mode')!='anonymous_public'
            or snapshot.get('credential_used') is not False
            or re.fullmatch(r'[0-9a-f]{40}',str(snapshot.get('commit_sha') or '')) is None
            or re.fullmatch(r'[0-9a-f]{40}',str(snapshot.get('tree_sha') or '')) is None):
        return None
    manifest=evidence.get('execution_input_manifest')
    if (not isinstance(manifest,dict) or manifest.get('schema')!='nico.snapshot-execution-inputs.v1'
            or manifest.get('snapshot_identity_verified') is not True
            or manifest.get('inventory_complete') is not True
            or manifest.get('snapshot_commit_sha')!=snapshot['commit_sha']
            or manifest.get('snapshot_tree_sha')!=snapshot['tree_sha']):
        return None
    paths=manifest.get('inventory_paths')
    if (not isinstance(paths,list) or not 1 <= len(paths) <= 20000
            or 'CMakeLists.txt' not in paths
            or not any(isinstance(path,str) and path.lower().endswith(_SOURCE_SUFFIXES) for path in paths)):
        return None
    if environ is None:
        environ=os.environ
    if release_revision is None:
        try:
            from nico.github_actions_proof_auth_v1 import expected_release_sha
            release_revision=expected_release_sha()
        except Exception:
            return None
    qualification=_settings(environ,release_revision)
    if qualification is None:
        return None
    return {'profile':PROFILE,'tool_version':'2.17.1','image_digest':qualification['image_config_id'],
        'configuration':{'schema':'nico.cpp-configure-first-contract.v1','platform':'linux/amd64',
            'expected_tree_sha':snapshot['tree_sha'],'project_options':{},'source_byte_limit':64*1024*1024,
            'baseline_execution':{'schema':'nico.cpp-baseline-execution.v2',
                'profile':'cpp-baseline-qualification-v1',
                'freeze_compilation_database':'after_configuration_before_build',
                'build_seconds':1200,'test_seconds':480,'test_case_seconds':60,'parallel':4},
            'capabilities':{'capture_generated_context':True,'project_compiler_evidence':True,
                'project_static_analysis':True,'extended_compiler_budget':True,'compiler_environment':True}},
        'targets':{},'limits':{'max_attempts':1,'wall_seconds':2420,'lease_seconds':300},
        'max_receipt_bytes':8*1024*1024}
