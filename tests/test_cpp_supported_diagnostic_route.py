"""Owned closed-route guards; no provider, token, Docker or target execution.

Only the operation-identity FunctionDef from the whole SHA-bound public source
is compiled. Environment mappings are owned test data, never execution proof.
"""
import ast
from copy import deepcopy
import hashlib
from pathlib import Path
import re
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'scripts/cpp_private_diagnostic_inputs.py'
EXPECTED_SOURCE_SHA = '1fd194b24cbaa083d4f072e657470840020bc38862d5facdeee780c26148fff4'
RAW = SOURCE.read_bytes()
if hashlib.sha256(RAW).hexdigest() != EXPECTED_SOURCE_SHA:
    raise AssertionError('reviewed_preparer_source_digest')
TREE = ast.parse(RAW)
DEFINITIONS = {node.name: node for node in TREE.body if isinstance(node, ast.FunctionDef)}
CONSTANTS = {}
for node in TREE.body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        if node.targets[0].id in {'REPOSITORY', 'IMAGE_BRANCH', 'IMAGE_WORKFLOW'}:
            CONSTANTS[node.targets[0].id] = ast.literal_eval(node.value)
        elif node.targets[0].id == 'SOURCE_PINS':
            if not isinstance(node.value, ast.Dict):
                raise AssertionError('literal_whole_source_pin_dictionary')
            CONSTANTS['SOURCE_PINS'] = {
                (CONSTANTS['IMAGE_WORKFLOW'] if isinstance(key, ast.Name) and key.id == 'IMAGE_WORKFLOW'
                 else ast.literal_eval(key)): ast.literal_eval(value)
                for key, value in zip(node.value.keys, node.value.values)
            }
SCOPE = {'re': re, 'REPOSITORY': CONSTANTS['REPOSITORY'], 'IMAGE_BRANCH': CONSTANTS['IMAGE_BRANCH']}
SELECTED = ast.Module(body=[DEFINITIONS['supported_operation_identity']], type_ignores=[])
exec(compile(ast.fix_missing_locations(SELECTED), '<sha-bound-supported-route>', 'exec'), SCOPE)
SUPPORTED = SCOPE['supported_operation_identity']
HEAD = 'a' * 40
ROUTES = {
    'same-image-parser-diagnostic': '.github/workflows/cpp-same-image-parser-diagnostic.yml',
    'same-image-full-static-diagnostic': '.github/workflows/cpp-same-image-full-static-diagnostic.yml',
}


def owned_environment(job):
    return {
        'GITHUB_JOB': job,
        'GITHUB_REPOSITORY': CONSTANTS['REPOSITORY'],
        'GITHUB_REF': 'refs/heads/' + CONSTANTS['IMAGE_BRANCH'],
        'GITHUB_EVENT_NAME': 'push',
        'GITHUB_RUN_ATTEMPT': '1',
        'RUNNER_ENVIRONMENT': 'github-hosted',
        'GITHUB_WORKFLOW_SHA': HEAD,
        'GITHUB_WORKFLOW_REF': CONSTANTS['REPOSITORY'] + '/' + ROUTES[job]
                               + '@refs/heads/' + CONSTANTS['IMAGE_BRANCH'],
    }


class Controls(unittest.TestCase):
    def test_only_two_exact_route_pairs_are_supported(self):
        definition = DEFINITIONS['supported_operation_identity']
        route_assignments = [node for node in definition.body if isinstance(node, ast.Assign)
                             and any(isinstance(target, ast.Name) and target.id == 'routes'
                                     for target in node.targets)]
        self.assertEqual(len(route_assignments), 1)
        self.assertEqual(ast.literal_eval(route_assignments[0].value), ROUTES)
        self.assertEqual(CONSTANTS['REPOSITORY'], 'BoneManTGRM/NICO')
        self.assertEqual(CONSTANTS['IMAGE_BRANCH'], 'diagnostic/v17-pinned-image-20261007')
        for job in ROUTES:
            with self.subTest(job=job):
                self.assertIs(SUPPORTED(owned_environment(job), HEAD), True)

    def test_job_and_workflow_may_not_impersonate_each_other(self):
        for job in ROUTES:
            for workflow in ROUTES.values():
                environment = owned_environment(job)
                environment['GITHUB_WORKFLOW_REF'] = (CONSTANTS['REPOSITORY'] + '/' + workflow
                                                     + '@refs/heads/' + CONSTANTS['IMAGE_BRANCH'])
                with self.subTest(job=job, workflow=workflow):
                    self.assertIs(SUPPORTED(environment, HEAD), workflow == ROUTES[job])
            for wrong_job in ('project-baseline-qualification', 'same-image-parser-diagnostic-extra',
                              'full-static', '', None):
                environment = owned_environment(job)
                environment['GITHUB_JOB'] = wrong_job
                with self.subTest(job=job, wrong_job=wrong_job):
                    self.assertIs(SUPPORTED(environment, HEAD), False)

    def test_every_authority_field_is_required(self):
        for job in ROUTES:
            original = owned_environment(job)
            for field in original:
                environment = deepcopy(original)
                environment.pop(field)
                with self.subTest(job=job, field=field):
                    self.assertIs(SUPPORTED(environment, HEAD), False)

    def test_wrong_repository_branch_event_attempt_runner_and_source_are_rejected(self):
        wrong = {
            'GITHUB_REPOSITORY': ('OtherOwner/NICO', 'BoneManTGRM/nico', 'BoneManTGRM/NICO/extra'),
            'GITHUB_REF': ('refs/heads/main', 'refs/pull/1/merge',
                           'refs/heads/' + CONSTANTS['IMAGE_BRANCH'] + '/extra'),
            'GITHUB_EVENT_NAME': ('pull_request', 'workflow_dispatch', 'workflow_run', 'schedule'),
            'GITHUB_RUN_ATTEMPT': ('2', '01', 1, ''),
            'RUNNER_ENVIRONMENT': ('self-hosted', 'github-hosted-extra', ''),
            'GITHUB_WORKFLOW_SHA': ('0' * 40, 'a' * 39, 'a' * 41),
            'GITHUB_WORKFLOW_REF': ('BoneManTGRM/NICO/.github/workflows/other.yml@refs/heads/'
                                    + CONSTANTS['IMAGE_BRANCH'],),
        }
        for job in ROUTES:
            for field, values in wrong.items():
                for value in values:
                    environment = owned_environment(job)
                    environment[field] = value
                    with self.subTest(job=job, field=field, value=value):
                        self.assertIs(SUPPORTED(environment, HEAD), False)
            for suffix in ('/extra', '@refs/heads/main', '?owned=value', ' '):
                environment = owned_environment(job)
                environment['GITHUB_WORKFLOW_REF'] += suffix
                with self.subTest(job=job, suffix=suffix):
                    self.assertIs(SUPPORTED(environment, HEAD), False)

    def test_malformed_head_cannot_become_its_own_source_identity(self):
        for job in ROUTES:
            for head in ('', None, 'a' * 39, 'a' * 41, 'A' * 40, 'g' * 40, 'a' * 40 + '\n'):
                environment = owned_environment(job)
                environment['GITHUB_WORKFLOW_SHA'] = head
                with self.subTest(job=job, head=head):
                    self.assertIs(SUPPORTED(environment, head), False)

    def test_actual_checked_sources_calls_guard_before_operation_git_verification(self):
        definition = DEFINITIONS['checked_sources']
        guard = [node for node in definition.body if isinstance(node, ast.Expr)
                 and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                 and node.value.func.id == 'require' and len(node.value.args) == 2
                 and isinstance(node.value.args[1], ast.Constant)
                 and node.value.args[1].value == 'operation_authority_identity']
        self.assertEqual(len(guard), 1)
        call = guard[0].value.args[0]
        self.assertIsInstance(call, ast.Call)
        self.assertEqual(ast.dump(call.func), "Name(id='supported_operation_identity', ctx=Load())")
        self.assertEqual([ast.dump(arg) for arg in call.args],
            ["Attribute(value=Name(id='os', ctx=Load()), attr='environ', ctx=Load())",
             "Name(id='head', ctx=Load())"])
        heads = [node for node in definition.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == 'head' for target in node.targets)]
        self.assertEqual(len(heads), 1)
        self.assertEqual(ast.dump(heads[0].value),
            "Call(func=Attribute(value=Attribute(value=Name(id='os', ctx=Load()), attr='environ', ctx=Load()), attr='get', ctx=Load()), args=[Constant(value='GITHUB_SHA'), Constant(value='')], keywords=[])")
        operation_calls = [node for node in ast.walk(definition) if isinstance(node, ast.Call)
                           and isinstance(node.func, ast.Attribute) and node.func.attr == 'checked_git_source'
                           and len(node.args) == 2 and isinstance(node.args[0], ast.Name)
                           and node.args[0].id == 'operation']
        self.assertEqual(len(operation_calls), 1)
        self.assertEqual(ast.dump(operation_calls[0].args[1]), "Name(id='head', ctx=Load())")
        self.assertLess(guard[0].lineno, operation_calls[0].lineno)
        verified_calls = [node for node in ast.walk(definition) if isinstance(node, ast.Call)
                          and isinstance(node.func, ast.Name) and node.func.id == 'verified_source_bodies']
        self.assertEqual(len(verified_calls), 1)
        self.assertLess(verified_calls[0].lineno, guard[0].lineno)

    def test_route_extension_keeps_nine_whole_source_pins(self):
        pins = CONSTANTS['SOURCE_PINS']
        self.assertEqual(set(pins), {
            'scripts/cpp_diagnostic_image_rebuild.py', 'scripts/cpp_diagnostic_image_inputs.json',
            'scripts/cpp_same_image_dependency_diagnostic.py', 'scripts/cpp_private_parser_worker.py',
            'scripts/cpp-parser-diagnostic-inputs/baseline_compiler.py',
            'scripts/cpp-parser-diagnostic-inputs/source_path_evidence.py',
            'scripts/cpp-parser-diagnostic-inputs/owned_fixture_harness.py',
            'nico/assessment_cpp_project_compiler.py', '.github/workflows/cpp-diagnostic-image-rebuild.yml',
        })
        for path, digest in pins.items():
            with self.subTest(path=path):
                self.assertIsNotNone(re.fullmatch('[0-9a-f]{64}', digest))
        # The actual whole source is SHA-bound above; this is not a new receipt
        # self-pinning route or a claim that a mocked environment ran on Actions.


if __name__ == '__main__':
    unittest.main()
