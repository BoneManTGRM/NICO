# Offline ordinary-repository shadow evaluation v1

This standalone comparator measures supplied test expectations against supplied automated
proposals. It never runs NICO assessments, loads candidate registers, fetches sources,
contacts a model/API, executes assessed source, accesses a database, or changes approval,
review, delivery, raw findings, scores, or historical reports. It is **shadow only**:
`human_review_required=true`, `client_delivery_blocked=true`, `approved=false`, and
`autonomy_qualified=false` on every result, including invalid inputs.

## Run locally

```sh
python -S scripts/offline_shadow_evaluation.py \
  --expected tests/fixtures/shadow/expected.json \
  --observed tests/fixtures/shadow/observed.json \
  --output /tmp/nico-shadow-example
python -m pytest -q tests/test_shadow_evaluation_v1.py
```

The output directory must not exist; its parent must exist. Inputs are read-only regular
files, limited to 2 MiB each; symlink files, devices and FIFOs are rejected. Each list is
limited to 10,000 rows, with total input constrained by the byte limit. No paths inside
JSON are followed. Outputs contain verbatim input bytes: keep private inputs and their
outputs private. Only the synthetic fixtures in this change are intended for publication.
Exit 0 means a measurement was produced, **not** that the proposal was safe, agreed with
the oracle, or passed a gate. Exit 2 means invalid/unreadable input or output failure.
There is no acceptance threshold or passing classification.

## Versioned input contract

The executable validators in `scripts/offline_shadow_evaluation.py` define the strict v1 contract;
`tests/fixtures/shadow/*.json` are complete executable examples. Every object rejects
unknown fields (including asserted aggregates or approval fields). Duplicate JSON keys,
case IDs, candidate IDs within a case, and material-finding IDs within a case are invalid.
IDs are case-local because different snapshots can legitimately reuse candidate identities.
Identity strings are 1–200 characters from the explicitly bounded token alphabet in
`token()`. Revisions are full 40-character lowercase hexadecimal commit identities.

Expected-answer root (`nico.shadow-expected.v1`):

- `schema`, `corpus_id`, `corpus_version`, `label_kind="test_expectations"`, `cases`.
- Each case: `case_id`, `scope`, `candidates`, `material_findings`.
- Scope: `source_id`, `repository`, `revision`, `source_schema`.
- Candidate: `candidate_id`, `expected_verdict` (`confirmed`, `not_actionable`, or
  `needs_review`). The last label means an unresolved expected answer, not ground truth
  that the finding is absent. It is counted and blocks a qualification interpretation.
- Material finding: `finding_id`, `candidate_ids`. Each mapping names confirmed expected
  candidates in that same case; one candidate may map to only one material finding.
  Multiple candidates may represent one seeded issue, counted once. An empty mapping
  deliberately represents a seeded issue for which no candidate was emitted. Every
  confirmed expected candidate must map to a material finding.

Observation root (`nico.shadow-observed.v1`):

- `schema`, identical `corpus_id` and `corpus_version`, `expected_sha256` (SHA-256 of
  exact expected file bytes), `cases`.
- Each case: `case_id`, identical `scope`, `status` (`complete`, `partial`, `unavailable`),
  `findings`. Unavailable cases must have no findings.
- Each finding: `candidate_id`, `technical_triage_verdict`, using the retained labels
  `confirmed`, `not_actionable`, `needs_review`.

`source_schema` is pinned to `nico.candidate-technical-triage.v2`. The scope fields bind
run/source, repository and immutable revision, while `expected_sha256` binds the exact
answer manifest. A changed revision, schema, corpus version or answer-file byte invalidates
comparison. This cannot establish freshness against an external current branch or the
truthfulness of a supplied scope; the caller must select the intended snapshot and oracle.

This is an explicit projection contract, not a new assessment engine or a generic register
importer. Prepare it from explicitly selected retained records without rerunning triage.
Preserve the original retained artifact separately. No default private corpus is loaded.
The existing retained triage/revalidation modules are not imported: their runtime
recommendations, occurrence-weighted workload percentages and aggregates are not benchmark
truth. Unexpected observed candidates invalidate the comparison until the oracle explicitly
maps/labels them; they cannot silently disappear from the denominator.

## Versioned output contract

`result.json` (`nico.shadow-result.v1`) contains fixed boundaries, limitations, input
filenames/byte lengths/checksums, measurement status, and block/unknown reasons.
For a measured run it contains corpus ID/version, **every expected case**, candidate and
material finding with its per-row outcome, computed counts, and metrics with machine-readable
`numerator`, `denominator`, `value`, and `unknown_reason`. A zero denominator always produces
`value=null` with `zero_denominator`, never 100%. An empty expected corpus is invalid.
The original expected file (including every case) and observation file are copied verbatim
as `expected.input.json` and `observed.input.json`. `checksums.json` binds these and the result.
No timestamps or random run IDs enter results, so repeated identical inputs produce identical
output bytes. Failed parsing retains readable bounded input bytes, emits no metrics, and
retains parsed valid expected cases where available. Missing/oversized/unreadable inputs are
explicit failures rather than empty observations; oversized inputs are not copied.

Candidate outcomes distinguish `correct_result`, `abstention`, `unsafe_dismissal`,
`incorrect_confirmation`, `unsupported_confirmation` (confirmation against unresolved
truth), and `missing_observation`. Dismissal against unresolved truth is conservatively
unsafe; it is not treated as a known false negative. Label agreement includes agreement to
abstain, but resolved-candidate correctness excludes unresolved oracle answers. Neither is
an end-to-end detection metric.

Material detection counts expected seeded issues with any mapped candidate present;
material confirmation requires at least one confirmed mapped candidate. An issue may be
detected yet incorrectly dismissed or abstained on. Missing candidates, missing cases,
and empty candidate mappings remain in the expected-material denominator. Omissions are
explicit `omitted_false_negative` outcomes; every unconfirmed expected issue is counted as
unresolved, including omissions. Partial cases retain observed decisions, but always
produce an incomplete-observation reason. True-zero credit requires an explicitly complete
case with no expected candidates or material findings; a missing or partial case cannot
receive that credit. Occurrence weights and input aggregates never affect metrics.

## Scope and limits

The synthetic v1 corpus exercises a correct confirmation/dismissal, an unsafe dismissal,
incorrect confirmation, abstention, unresolved expected answer, omitted candidate,
never-emitted material issue, missing case and explicit true-zero case. Adversarial tests
cover malformed/missing/partial/foreign inputs, stale answers, duplicates, unknown labels,
forged aggregates, repeatability, nonmutation, bounded files and zero denominators.

This is a measurement foundation, not the complete corpus required by `METRICS.md` and not
current production calibration. It does not validate evidence semantics, severity,
remediation, source provenance authenticity, or answer-manifest completeness. It does not
measure all METRICS targets, use legacy report-value thresholds, invent an acceptable
false-negative threshold, or qualify autonomy. Test expectations are never real reviewer
identities, specialist evidence, approval or delivery authorization. Existing golden report
fixtures and acceptance checks remain unchanged; #1878 evidence-request preparation and
#1879 bounded exception-handler facts are not duplicated.
