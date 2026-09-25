from nico.assessment_cpp_production_selection import select_configure_first_contract

RELEASE='a'*40
TREE='b'*40
IMAGE='sha256:'+'c'*64

def repo_step(paths=None):
    paths=paths or ['CMakeLists.txt','src/a.cpp','include/a.h']
    snapshot={'status':'attached','exact_commit_verified':True,'provider':'github',
        'access_mode':'anonymous_public','credential_used':False,
        'commit_sha':'d'*40,'tree_sha':TREE,'snapshot_id':'snap'}
    return {'status':'complete','repository_snapshot':snapshot,
        'repository_evidence':{'execution_input_manifest':{
            'schema':'nico.snapshot-execution-inputs.v1','snapshot_commit_sha':'d'*40,
            'snapshot_tree_sha':TREE,'snapshot_identity_verified':True,'inventory_complete':True,
            'inventory_paths':paths}}}

def env():
    return {'NICO_CPP_CONFIGURE_FIRST_ENABLED':'1',
        'NICO_ASSESSMENT_WORKER_DISPATCH_ENABLED':'1',
        'NICO_CPP_CONFIGURE_FIRST_IMAGE_CONFIG_ID':IMAGE,
        'NICO_CPP_CONFIGURE_FIRST_QUALIFIED_RELEASE':RELEASE,
        'NICO_CPP_CONFIGURE_FIRST_QUALIFICATION_RUN_ID':'12345',
        'NICO_CPP_CONFIGURE_FIRST_QUALIFICATION_ARTIFACT_SHA256':'e'*64}

def test_release_owned_selector_builds_generic_configure_first_contract():
    result=select_configure_first_contract(repo_step(),environ=env(),release_revision=RELEASE)
    assert result['profile']=='cpp-configure-first-v2'
    assert result['image_digest']==IMAGE
    assert result['configuration']['expected_tree_sha']==TREE
    assert result['configuration']['schema']=='nico.cpp-configure-first-contract.v2'
    assert result['configuration']['project_option_policy']=='conservative-cmake-v1'
    assert 'project_options' not in result['configuration']
    assert result['targets']=={}
    assert result['limits']=={'max_attempts':1,'wall_seconds':2420,'lease_seconds':300}

def test_selector_is_fail_closed_without_generic_cpp_cmake_or_release_proof():
    assert select_configure_first_contract(repo_step(['README.md']),environ=env(),release_revision=RELEASE) is None
    assert select_configure_first_contract(repo_step(['src/a.cpp']),environ=env(),release_revision=RELEASE) is None
    bad=env(); bad['NICO_CPP_CONFIGURE_FIRST_QUALIFIED_RELEASE']='e'*40
    assert select_configure_first_contract(repo_step(),environ=bad,release_revision=RELEASE) is None
    bad=env(); bad['NICO_ASSESSMENT_WORKER_DISPATCH_ENABLED']='0'
    assert select_configure_first_contract(repo_step(),environ=bad,release_revision=RELEASE) is None
    bad=env(); bad['NICO_CPP_CONFIGURE_FIRST_QUALIFICATION_RUN_ID']='0'
    assert select_configure_first_contract(repo_step(),environ=bad,release_revision=RELEASE) is None
    bad=env(); bad['NICO_CPP_CONFIGURE_FIRST_QUALIFICATION_ARTIFACT_SHA256']='bad'
    assert select_configure_first_contract(repo_step(),environ=bad,release_revision=RELEASE) is None

def test_selector_requires_anonymous_exact_snapshot_and_uses_no_repo_name_rule():
    first=repo_step(); first['repository_snapshot']['access_mode']='authenticated_read_only'
    first['repository_snapshot']['credential_used']=True
    assert select_configure_first_contract(first,environ=env(),release_revision=RELEASE) is None
    result=select_configure_first_contract(repo_step(),environ=env(),release_revision=RELEASE)
    assert 'bitcoin' not in repr(result).lower()

def test_snapshot_handler_passes_only_internal_selected_contract(monkeypatch):
    from nico import snapshot_assessment_handlers as handlers
    selected={'profile':'synthetic-internal'}
    monkeypatch.setattr('nico.assessment_cpp_production_selection.select_configure_first_contract',
                        lambda step:selected)
    seen={}
    def start(payload,**kwargs):
        seen.update(kwargs)
        return {'status':'queued','scan_id':'scan'}
    monkeypatch.setattr(handlers,'start_snapshot_scan',start)
    outputs={'repo_evidence':repo_step()}
    context={'run_id':'run','repository':'owner/repo','customer_id':'c','project_id':'p',
        'authorized_by':'owner','authorization_scope':'assessment','run_scanners':True,'tools':[]}
    result=handlers._snapshot_scanner_handler(context,outputs)
    assert result['status']=='queued' and seen=={'cpp_contract':selected}
