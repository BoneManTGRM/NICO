# Bounded Python discovery candidates

NICO's installed package registers two additive Bandit plugins. Bandit's normal
`bandit -r . -f json` command discovers them through `bandit.plugins` entry points.
The tool identity remains `bandit`; the distinct rules are:

| Rule | Candidate | Existing direct rule |
| --- | --- | --- |
| B951 / nico_requests_bound_false | `requests.get(..., verify=flag)` when a sole local literal False assignment reaches the returned call | B501 |
| B952 / nico_hashlib_getattr_md5 | `getattr(hashlib, 'md5')(data)` directly returned or followed by digest()/hexdigest() | B324 |

These are review candidates, not confirmed vulnerabilities, approved dispositions
or autonomous delivery authority. Both have MEDIUM severity and MEDIUM confidence;
the existing Bandit classifier leaves them `needs_human_review`, `approved=false`.
No triage/scoring/approval/delivery policy is changed. MD5 is not universally a
vulnerability; context and security-sensitive use must be reviewed. Direct forms
remain owned by the existing rules, avoiding duplicate native/additional reports.

## Supported scope

Analysis uses only Bandit's already-parsed AST; no source read, traversal, target
import or execution is added. The plugins do not import `nico` application startup.

The supplement intentionally accepts a small syntactic subset:

- Canonical, unaliased `import requests` / `import hashlib`, exactly once, before
  the containing top-level function; no conflicting protected import names.
- A module containing only ordinary imports, undecorated top-level functions and
  string docstrings. Nonliteral annotations/defaults, type parameters and other
  module statements are outside this initial scope.
- A function with optional docstrings and single-name literal assignments followed
  by a return. No reassignment, parameter overwrite, nested scope, branches,
  loops, exceptions or preceding call is followed.
- TLS uses a named local whose sole value is exactly False (not integer zero), a
  direct requests HTTP verb, and simple literal/name arguments without **kwargs.
- Hash selection uses builtin `getattr`, the canonical hashlib name, the literal
  lowercase `md5`, exactly two selector arguments, and simple constructor arguments.
  `usedforsecurity=False` or unknown values are not promoted. Computed names,
  aliases, other receivers, wrappers and later invocation of a saved constructor
  are outside scope.

Parameters/local bindings of protected names, global/nonlocal declarations, known
dynamic evaluation/mutation calls and any attribute/subscript writes in the module
suppress the supplement. These finite guards are not general interprocedural alias
analysis or proof against external/dynamic monkeypatching. Ordinary canonical
library semantics are assumed; candidate-only wording preserves that uncertainty.
Unsupported forms remain unsupported, not clean or safe by inference.

AST work is cached per module, limited to 10,000 visited plus pending nodes and
64 levels of depth. A limit writes an explicit stderr coverage warning and yields
no supplemental candidate. Bandit's native traversal/time/output limits still
apply; these limits do not claim to bound Bandit's own parser. Malformed sources
retain native Bandit errors. Native nosec and rule filtering still apply, with
separate B951/B952 identities. Excluding B501 alone does not exclude B951.

## Installation and runtime boundary

The plugins must be in the SAME Python installation as the invoked Bandit binary.
Installing only requirements or copying a source checkout is insufficient.
Setuptools' existing `nico*` package selection includes the inert `nico_bandit`
package; its entry points are wheel metadata, not editable-install side effects.

The existing root Dockerfile installs requirements and then
`python -m pip install --no-cache-dir --no-deps .` (line 101 at the qualified base),
so an ordinary rebuilt image installs these plugins without deployment-file changes.
The frozen-sha scanner proof and scanner-live-contract workflows also install the
project. The assessment-worker workflow's requirements-only step is a controller
installation, not evidence that an arbitrary separately selected worker image has
these plugins. That image must independently install this revision's package.
The phase9-bandit-reliability workflow installs Bandit alone: it will continue to
run native rules without these additions until its installation is coordinated.
No workflow, worker image, deployment or release was changed in this slice.

Qualification checks wheel contents and entry-point metadata, installs the wheel
non-editably into an isolated copy of the existing runtime without network or new
dependencies, and invokes the actual ordinary base scanner subprocess and canonical
Bandit JSON runner. This establishes installed-package discovery in the local
runtime. It does not establish that a hosted/deployed image has been rebuilt or
that technical triage/full assessment/delivery has run.

## Independent expectations and qualification

`tests/fixtures/bounded_python_candidates/cases.json` is a byte-identical copy of
the accepted independent mutation manifest. Expectations remain source mutations,
not scanner-derived labels. The four clean controls are clean only for the two
specified candidate classes. B951 maps to the TLS class, B952 to weak-hash
candidate discovery; original B501/B324 remain separate native observations.
The word `defect` in the inherited manifest denotes mutation membership, never a
confirmed application vulnerability.

Run the affected tests with this revision's package installed alongside Bandit:

```sh
python -m pip install --no-deps .
python -m pytest -q tests/test_bounded_python_candidates.py tests/test_scanner_tool_runners.py tests/test_bandit_json_execution_v61.py tests/test_run_bandit_reliably.py tests/test_bandit_triage.py tests/test_hosted_bandit_triage_workflow_patch.py tests/test_hosted_static_scanner_execution_patch.py
```

Historical experiment source identities and evidence remain untouched. Before/after
local qualification copies their exact Git repositories, retains native JSON,
commands, stderr, source/runtime revisions, wheel hashes and candidate mappings.
It compares all eight members, including omissions, unexpected and incomplete
observations. Local qualification artifacts remain shadow-only,
`human_review_required=true`, `client_delivery_blocked=true`,
`autonomy_qualified=false`; no acceptance thresholds or METRICS claims change.

## Coordination

Base inspected: `69004febcdefb9e96439b8bf303a1c245f3e1112`.
#1870 inspected head: `2ace5170f5e5ab67e0f3acf640efbf57ef8e0f8d`.
Its comprehensive_native_providers.py hunk adds failed-snapshot diagnostic output;
its worker_execution.py hunk changes process-group absence probing. This change
touches neither file and adds no source traversal or process supervision. There is
no integration-order dependency at these pins. No #1870 job was rerun. #1881 and
its ready-state operation remain separately owned and untouched.
