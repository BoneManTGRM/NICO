# Exact Cppcheck source-digest observations

Security Audit Evidence run [38305087110](https://github.com/BoneManTGRM/NICO/actions/runs/38305087110)
failed on six unapproved Gitleaks observations after reporting PR1721 merged at
`3dcdb6203068510917b033117ec8226e91ac532d`. The merge changed seven reporting/test
files, not these source maps. Neither evidence commit below is an ancestor of that
main revision. The workflow uses a full-history checkout and Gitleaks git-history
scan, so observations from fetched divergent history can block the gate.

## Independently verified source provenance

| Commit | Evidence map | Git blob |
| --- | --- | --- |
| `6eff8889db11a3ab31c3b04f5af053edb542d6e8` | `docs/evidence/cppcheck-composed-runtime-20261012/fixed-final-source-sha256.json` | `5439b021471f10ef97e7bf6f62da4d860eafd9a1` |
| `fc9a0a75ac2cdd614304d7483eb8cbaf3b161b01` | `docs/evidence/cppcheck-pr1712-ast-integration-20261012/composed-source-sha256.json` | `bee506622edc8c4b2810d1a752b1ddf5499c5a55` |

Fresh official Cppcheck source objects were fetched at pinned upstream commit
`ac9db3069b9f90e81e126a090b99ad456e122cf8`. For each NICO evidence commit,
its exact `repair_cppcheck_placement_ast.py` and `repair_cppcheck_header_grammar.py`
were applied to copied upstream source bytes, in that order. Both patchers
validated their immutable upstream identities and anchors before modification.

SHA256 recomputation of all three resulting files matched the corresponding map:
`lib/token.cpp` (line 8), `lib/tokenize.cpp` (line 9), `lib/tokenlist.cpp` (line 10).
The freshly generated grammar receipts also matched each recorded receipt in
full, including script identity and source-before/source-after identities:
`fixed-final-grammar-receipt.json` and `grammar-receipt.json`, respectively.
Thus these six values are source-file digests, not credentials. Both receipts
retain `native_qualification_completed: false`. No C++ build or binary ran.

Source-map byte hashes:

- Fixed map: `5918717801345db1629d457fcb12c7657e63e237b6c8ce80f3991abb6d163800`.
- Composed map: `d4e893a2c0e16775a7b5b7c464e030b7d0a3ad2602c5885fc712bd7810f51910`.

## Exact observation verification

The workflow's pinned Gitleaks 8.30.1 archive was verified against its existing
installer checksum `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`.
A bounded local redacted scan of each exact commit (`--log-opts=COMMIT^..COMMIT`),
using unchanged `.gitleaks.toml`, reproduced these six records; both scans exited 1
because findings were retained. This security-scanner execution completed before
the subsequent instruction prohibiting further native binaries. No further
native execution followed. No Library or denied artifact-transfer route was retried.

All six records use `generic-api-key`, `Secret=REDACTED`, start column 9, and the
exact commit/path/line fingerprint. Matching text and positions:

| Source name | Redacted Match | Start/End line | End column |
| --- | --- | --- | --- |
| token.cpp | `token.cpp": "REDACTED"` | 8 | 86 |
| tokenize.cpp | `tokenize.cpp": "REDACTED"` | 9 | 89 |
| tokenlist.cpp | `tokenlist.cpp": "REDACTED"` | 10 | 90 |

The scanner records have no Verified field. The disposition accepts its absence
or boolean false only. Full hosted artifact 11772755785 was not materialized in
this session; the parent independently retains that artifact. Local reproduction
is evidence of these observation shapes, not a claimed replay of the whole audit.

## Narrow correction and validation

The existing gate now assigns `approved_public_source_hash` only to these six
immutable observations. It retains scanner artifacts, hashes, counts and triage.
It does not modify scanner configuration, omit paths, suppress findings, accept
hexadecimal strings by class, or change the acceptance policy. Redacted evidence
relies on the immutable commit/path/position binding already used by this gate;
it does not infer a hidden value from REDACTED alone.

Regression tests cover all six matches, missing fields, unknown commits with
consistent fingerprints, crossed commit/path pairs, changed values, rules,
positions, types and Verified status. Mixed approved/unmatched credential records
still block. Manifest human-review and client-delivery restrictions remain intact.
The six freshly reproduced scanner records also pass the narrow classifier while
remaining retained. Focused command:

```sh
/workspace/nico-venv/bin/python -m pytest -q tests/test_security_audit_gate.py tests/test_security_audit_pr1641_deployment.py tests/test_security_audit_pr1644_deployment.py tests/test_security_audit_secret_capture.py
```

Before implementation, the new tests produced 2 expected failures and 186 passes.
Final focused suite: **330 passed in 3.56s**; `git diff --check` passed.
No hosted audit rerun is claimed.
No publication, merge, deployment, qualification, provider or database operation
was performed. Atlas must independently review this diff before publication.
