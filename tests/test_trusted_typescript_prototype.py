"""Owned synthetic inputs only; these tests do not qualify production isolation."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / 'scripts/trusted_typescript_prototype.cjs'
# Existing provisioned compiler, never resolve from an assessed repository.
COMPILER = next((p for p in (ROOT/'apps/web/node_modules/typescript', Path('/workspace/NICO/apps/web/node_modules/typescript'))
                 if (p/'package.json').is_file()), ROOT/'apps/web/node_modules/typescript')
NODE = shutil.which('node')


def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def manifest(files=None, options=None, config_extra=None):
    data = {'src/main.ts': 'const answer: number = 42;\n'} if files is None else dict(files)
    config = {'compilerOptions': {'strict': True, 'target': 'es2020', 'module': 'commonjs', **(options or {})},
              'include': ['src/**/*.ts'], **(config_extra or {})}
    data['tsconfig.json'] = json.dumps(config)
    rows = [{'path': name, 'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest(),
             'kind': 'config' if name.endswith('.json') else 'source'} for name, text in sorted(data.items())]
    body = {'schema': 'nico.typescript.frozen-input.v1',
            'identity': {'repository': 'owned/synthetic', 'commit_sha': 'a'*40,
                         'run_id': 'owned_fixture', 'snapshot_id': 'synthetic_snapshot'},
            'config': 'tsconfig.json', 'files': rows}
    return {'manifest': body, 'manifest_sha256': digest(body)}


@pytest.fixture(scope='module')
def anchors():
    if not NODE or not COMPILER.is_dir():
        pytest.skip('Owned native prototype needs existing Node and TypeScript 6.0.3; no installation attempted')
    libs = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((COMPILER/'lib').glob('lib*.d.ts'))}
    return {'package_sha256': hashlib.sha256((COMPILER/'package.json').read_bytes()).hexdigest(),
            'compiler_sha256': hashlib.sha256((COMPILER/'lib/typescript.js').read_bytes()).hexdigest(),
            'libraries_sha256': digest(libs)}


def run(request, anchors):
    harness = "const p=require(process.argv[1]); const fs=require('node:fs'); const a=JSON.parse(process.argv[3]); const r=p.createTrustedRunner(process.argv[2],a); process.stdout.write(JSON.stringify(r(JSON.parse(fs.readFileSync(0,'utf8')))));"
    result = subprocess.run([NODE, '--max-old-space-size=256', '-e', harness, str(PROGRAM), str(COMPILER), json.dumps(anchors)],
                            input=json.dumps(request), text=True, capture_output=True, timeout=15,
                            env={'PATH': '/nonexistent', 'NODE_OPTIONS': '', 'NODE_PATH': '', 'LANG': 'C.UTF-8'})
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_clean_owned_project_has_bound_receipt(anchors):
    req = manifest()
    before = digest(req)
    result = run(req, anchors)
    assert result['status'] == 'complete'
    assert result['diagnostics'] == []
    receipt = result['receipt']
    assert receipt['manifest_sha256'] == req['manifest_sha256']
    assert receipt['identity'] == req['manifest']['identity']
    assert receipt['compiler']['version'] == '6.0.3'
    assert receipt['compiler']['compiler_sha256'] == anchors['compiler_sha256']
    assert receipt['os_isolation_verified'] is False
    assert receipt['qualified_for_production'] is False
    assert receipt['emitted_files'] == 0
    assert receipt['receipt_sha256'] == digest({k:v for k,v in receipt.items() if k!='receipt_sha256'})
    assert digest(req) == before


def test_cross_file_semantic_error_is_preserved(anchors):
    result = run(manifest({'src/a.ts': 'export const value = "wrong";',
                           'src/main.ts': 'import {value} from "./a"; const n: number = value;'}), anchors)
    assert result['status'] == 'complete'
    assert result['clean'] is False
    assert any(d['code'] == 2322 and d['file'] == 'src/main.ts' for d in result['diagnostics'])
    assert result['findings'] == result['diagnostics']


@pytest.mark.parametrize('files', [
    {'src/main.ts': 'import {x} from "missing-package"; x();'},
    {'src/main.ts': 'import "../.next/types/routes.d.ts";'},
    {'src/main.ts': '/// <reference path="missing.d.ts" />\nconst x = 1;'},
    {'src/main.ts': 'import x from "../../outside";'},
])
def test_missing_closure_is_never_complete(files, anchors):
    result = run(manifest(files), anchors)
    assert result['status'] == 'incomplete'
    assert result['clean'] is False
    assert result['closure_failures']


@pytest.mark.parametrize('extra', [{'extends': '../outside.json'}, {'references': [{'path': '../other'}]}])
def test_unsupported_config_fails_closed(extra, anchors):
    result = run(manifest(config_extra=extra), anchors)
    assert result['status'] == 'incomplete'


@pytest.mark.parametrize('options', [{'plugins': [{'name': 'evil'}]}, {'noCheck': True}, {'noResolve': True}, {'types': ['missing']}])
def test_plugin_and_disabled_checking_rejected(options, anchors):
    assert run(manifest(options=options), anchors)['status'] == 'incomplete'


@pytest.mark.parametrize('path', ['../escape.ts', '/tmp/escape.ts', 'src/../escape.ts', 'src\\escape.ts', '__proto__'])
def test_path_escape_rejected(path, anchors):
    req = manifest({path: 'const x = 1;'})
    assert run(req, anchors)['status'] == 'incomplete'


def test_digest_and_identity_negative_controls(anchors):
    req = manifest(); req['manifest']['files'][0]['text'] += 'tamper'
    assert run(req, anchors)['status'] == 'incomplete'
    req = manifest(); req['manifest']['identity']['commit_sha'] = 'wrong'
    req['manifest_sha256'] = digest(req['manifest'])
    assert run(req, anchors)['status'] == 'incomplete'


def test_empty_and_dependency_bundle_do_not_pass(anchors):
    assert run(manifest({}), anchors)['status'] == 'incomplete'
    req = manifest(); req['manifest']['files'][0]['kind'] = 'dependency'
    req['manifest_sha256'] = digest(req['manifest'])
    result = run(req, anchors)
    assert result['status'] == 'incomplete'
    assert 'offline_bundle_verification_unimplemented' in result['reason']


def test_malformed_config_and_source_diagnostics(anchors):
    req = manifest(); row = next(r for r in req['manifest']['files'] if r['kind']=='config')
    row['text'] = '{ broken'; row['sha256'] = hashlib.sha256(row['text'].encode()).hexdigest()
    req['manifest_sha256'] = digest(req['manifest'])
    result = run(req, anchors)
    assert result['status'] == 'incomplete' and result['diagnostics']
    result = run(manifest({'src/main.ts': 'const x: = ;'}), anchors)
    assert result['status'] == 'complete' and result['diagnostics'] and not result['clean']


def controller_tools(anchors):
    from nico.trusted_typescript_prototype_v1 import FixtureTools
    node = Path(NODE).resolve()
    return FixtureTools(node, hashlib.sha256(node.read_bytes()).hexdigest(), COMPILER, anchors)


def test_bounded_controller_validates_receipt(anchors):
    from nico.trusted_typescript_prototype_v1 import run_owned_fixture
    req = manifest()
    result = run_owned_fixture(req, tools=controller_tools(anchors), expected_identity=req['manifest']['identity'])
    assert result['status'] == 'complete', result
    assert result['execution']['capture_complete'] is True
    assert result['execution']['cpu_limit_verified'] is False
    assert result['native_stdout']


@pytest.mark.parametrize('limit,reason', [('wall_seconds', 'wall_timeout'), ('output_bytes', 'output_budget_exceeded'), ('input_bytes', 'controller_input_budget')])
def test_controller_budget_failure_cannot_credit_success(limit, reason, anchors):
    from nico.trusted_typescript_prototype_v1 import FixtureLimits, run_owned_fixture
    req = manifest()
    value = .000001 if limit == 'wall_seconds' else 1
    result = run_owned_fixture(req, tools=controller_tools(anchors), expected_identity=req['manifest']['identity'], limits=FixtureLimits(**{limit:value}))
    assert result['status'] == 'incomplete' and result['clean'] is False
    assert result['reason'] == reason
    assert result['receipt'] is None


def test_compiler_and_node_identity_mismatch(anchors):
    from dataclasses import replace
    from nico.trusted_typescript_prototype_v1 import run_owned_fixture
    req = manifest(); tools = controller_tools(anchors)
    for broken in (replace(tools, node_sha256='0'*64), replace(tools, compiler_anchors={**anchors, 'compiler_sha256':'0'*64})):
        result = run_owned_fixture(req, tools=broken, expected_identity=req['manifest']['identity'])
        assert result['status'] == 'incomplete' and result['receipt'] is None
    result = run_owned_fixture(req, tools=tools, expected_identity={**req['manifest']['identity'], 'commit_sha':'b'*40})
    assert result['reason'] == 'controller_identity_mismatch'


def test_transport_rejects_corruption_and_forged_clean(anchors):
    from nico.trusted_typescript_prototype_v1 import _validate_result
    req = manifest(); result = run(req, anchors)
    for raw in (b'{', b'{"status":"complete","status":"incomplete"}', b'\xff', json.dumps({**result, 'clean':False}).encode()):
        with pytest.raises((ValueError, UnicodeError)):
            _validate_result(raw, req, anchors)


@pytest.mark.parametrize('files,options', [
    ({'src/main.ts':'const x=1;', 'src/broken.d.ts':'declare const x: MissingType;'}, {'skipLibCheck':True}),
    ({'src/main.js':'/** @type {number} */ const n="bad";'}, {'allowJs':True, 'checkJs':False}),
    ({'src/main.ts':'const target: string="./unknown"; import(target);'}, {}),
])
def test_review_closure_negative_controls(files, options, anchors):
    assert run(manifest(files, options), anchors)['status'] == 'incomplete'


def test_source_is_parsed_never_executed_and_no_files_written(tmp_path, anchors):
    sentinel = tmp_path/'must-not-exist'
    source = f'require("node:fs").writeFileSync({json.dumps(str(sentinel))}, "bad");\nthrow new Error("owned fixture must never execute");'
    result = run(manifest({'src/main.ts':source}), anchors)
    assert result['status'] == 'incomplete'
    assert not sentinel.exists()
    assert list(tmp_path.iterdir()) == []


def test_source_symlink_claim_and_duplicate_entries_rejected(anchors):
    req = manifest(); req['manifest']['files'][0]['symlink'] = '/outside'
    req['manifest_sha256'] = digest(req['manifest'])
    assert run(req, anchors)['status'] == 'incomplete'
    req = manifest(); req['manifest']['files'].append(req['manifest']['files'][0].copy())
    req['manifest_sha256'] = digest(req['manifest'])
    assert run(req, anchors)['status'] == 'incomplete'


def test_diagnostic_text_and_related_information_survive(anchors):
    result = run(manifest({'src/main.ts':'interface Person { name: string; }\nconst p: Person = {name: 123};'}), anchors)
    finding = next(d for d in result['diagnostics'] if d['code']==2322)
    assert "number" in finding['message'] and finding['related']
    assert result['findings'] == result['diagnostics']


def test_generated_bundle_is_explicitly_unsupported(anchors):
    req = manifest(); req['manifest']['files'][0]['kind'] = 'generated'
    req['manifest_sha256'] = digest(req['manifest'])
    assert run(req, anchors)['reason'] == 'offline_bundle_verification_unimplemented'


def test_clean_cross_file_project_and_no_emit_options(anchors):
    result = run(manifest({'src/a.ts':'export const value = 42;',
                           'src/main.ts':'import {value} from "./a"; const n: number = value;'},
                          {'incremental':True, 'noEmit':False}), anchors)
    assert result['status'] == 'complete' and result['clean'] is True
    assert result['receipt']['effective_options']['noEmit'] is True
    assert result['receipt']['effective_options']['incremental'] is False
    assert result['receipt']['emitted_files'] == 0


def test_input_size_and_file_count_bounds(anchors):
    req = manifest({'src/main.ts':' '*(2*1024*1024)})
    assert run(req, anchors)['reason'] == 'source_byte_budget'
    req = manifest({f'src/{i}.ts':'export {};' for i in range(256)})
    assert run(req, anchors)['reason'] == 'source_file_budget'


def test_library_digest_and_symlinked_compiler_rejected(tmp_path, anchors):
    from dataclasses import replace
    from nico.trusted_typescript_prototype_v1 import run_owned_fixture
    req = manifest(); tools = controller_tools(anchors)
    alias = tmp_path/'compiler'; alias.symlink_to(COMPILER, target_is_directory=True)
    for broken in (replace(tools, compiler_root=alias), replace(tools, compiler_anchors={**anchors, 'libraries_sha256':'0'*64})):
        result = run_owned_fixture(req, tools=broken, expected_identity=req['manifest']['identity'])
        assert result['status'] == 'incomplete' and result['receipt'] is None


def test_incomplete_receipt_cannot_be_tampered(anchors):
    from nico.trusted_typescript_prototype_v1 import _validate_result
    req = manifest({'src/main.ts':'import "missing";'})
    result = run(req, anchors)
    assert result['status'] == 'incomplete' and result['receipt']
    result['receipt']['identity']['commit_sha'] = 'b'*40
    with pytest.raises(ValueError):
        _validate_result(json.dumps(result).encode(), req, anchors)


def test_controller_retains_native_type_diagnostics(anchors):
    from nico.trusted_typescript_prototype_v1 import run_owned_fixture
    req = manifest({'src/main.ts':'const n: number = "bad";'})
    result = run_owned_fixture(req, tools=controller_tools(anchors), expected_identity=req['manifest']['identity'])
    assert result['status'] == 'complete' and not result['clean']
    assert result['findings'] == result['diagnostics']
    assert json.loads(result['native_stdout'])['diagnostics'] == result['diagnostics']


def test_missing_compiler_library_is_incomplete(anchors):
    result = run(manifest({'src/main.ts':'/// <reference lib="not-a-real-lib" />\nconst x=1;'}), anchors)
    assert result['status'] == 'incomplete' and result['closure_failures']
    assert any(d['code'] == 2726 for d in result['diagnostics'])


def test_per_file_hash_is_independently_verified(anchors):
    req = manifest(); req['manifest']['files'][0]['text'] += ' changed'
    req['manifest_sha256'] = digest(req['manifest'])
    assert run(req, anchors)['reason'] == 'source_digest'


def test_limits_cannot_be_increased(anchors):
    from nico.trusted_typescript_prototype_v1 import FixtureLimits, run_owned_fixture
    req = manifest()
    result = run_owned_fixture(req, tools=controller_tools(anchors), expected_identity=req['manifest']['identity'], limits=FixtureLimits(wall_seconds=30))
    assert result['reason'] == 'controller_limits'


def test_package_script_data_is_not_executed(tmp_path, anchors):
    sentinel = tmp_path/'script-must-not-run'
    req = manifest({'src/main.ts':'export const x=1;',
                    'package.json':json.dumps({'scripts':{'preinstall':f'touch {sentinel}'}})})
    result = run(req, anchors)
    assert result['status'] == 'complete' and result['clean']
    assert not sentinel.exists()
