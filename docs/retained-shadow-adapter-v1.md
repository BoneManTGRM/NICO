# Retained register shadow adapter v1

This local driver removes per-candidate verdict transcription into the #1881 comparator.
It reads only explicitly selected files, copies existing `technical_triage_verdict`
values, and calls the standalone comparator's pure validation/comparison functions.
It never imports NICO application startup, reruns inference or retained-triage
revalidation, loads a default/private corpus, executes assessed sources, or calls any
network, database, model or API. All results are shadow-only, human-review-required,
client-delivery-blocked, unapproved and not autonomy-qualified. No scores, dispositions,
reports or runtime gates change.

## Supported seam and limits

Only exported `nico.canonical-scanner-findings.v1` register JSON is supported. The shape
comes from `nico/comprehensive_native_providers_v5.py` and the candidate-register export
in `nico/comprehensive_artifact_manifest_approval_v1.py`. Its current `exact_commit_sha`,
`assessment_subject.repository`, `technical_triage.artifact_schema` equal to
`nico.candidate-technical-triage.v2`, and `findings[].candidate_id` must be present.
A finding's `exact_commit_sha`, if present, must match too. No aliases, fuzzy ID matching,
case folding or label normalization is performed. Registers lacking these exact bindings
are rejected. Compressed historical v1 codebooks, whole assessment envelopes, CSV,
and evidence-request packets are deliberately unsupported.

**The register does not intrinsically identify the source run.** The independent selection
manifest explicitly supplies source/run identity and binds it to exact retained bytes.
Repository and current revision are cross-checked against the register; source identity
is a caller assertion, not authenticated provenance. Nested triage
`source_target_commit_sha` describes prior lineage, not the assessed current revision.
Hashes and claimed scope do not prove authenticity, oracle completeness, current branch
freshness, or that historical recommendations are still sound. This adapter preserves
verdicts even where current revalidation might change them; it never performs that work.

Every selected case projects as `partial`, even if retained status/totals say complete.
A register cannot establish whole-assessment completeness or independently prove a
true-zero case. Expected unselected cases remain missing. Expected candidates absent
from a selected register remain absent. A retained row with an absent or null verdict
is listed explicitly as missing-verdict and contributes no invented decision. An empty
string, unknown label or wrong type is invalid, not an abstention. Existing `needs_review`
values are preserved as abstentions. Additional unmapped candidates invalidate the entire
projection until the independent expected manifest explicitly accounts for them.

Candidate discovery, triage and complete-assessment quality remain distinct:
`retained_candidate_ids` measures row presence; `verdicts_transcribed` counts existing
verdicts copied; the existing comparator's material detection metric counts **verdict-bearing**
candidates. A row without a verdict is consequently a missing comparator observation, not
proof that discovery failed. Read the adapter's missing-verdict/absent-ID lists alongside
comparison metrics. Expected material issues and unresolved expected answers always stay
in their original denominators. No threshold or passing/autonomy classification exists.

## Input and execution

The independent expected manifest remains `nico.shadow-expected.v1`, unchanged.
The strict `nico.shadow-selection.v1` manifest contains exactly:

- `schema`, `expected_sha256` (exact expected file bytes), `cases`.
- Each case: `case_id`, `scope` (the comparator's exact source/repository/revision/schema
  object), `register_sha256` (exact selected register bytes).

All manifest IDs must match expected cases. Source identities cannot be repeated across
selected cases. The `--record CASE_ID PATH` arguments must match selection cases exactly;
all rows in each selected register are processed. No per-row selection or silently
ignored files are supported. Neither expected labels nor corpus membership is inferred
from retained observations. The operator must supply an independently authored oracle.

```sh
python -S scripts/retained_shadow_adapter.py \
  --expected tests/fixtures/shadow_adapter/expected.json \
  --selection tests/fixtures/shadow_adapter/selection.json \
  --record mixed tests/fixtures/shadow_adapter/mixed.json \
  --record zero tests/fixtures/shadow_adapter/zero.json \
  --output /tmp/nico-retained-shadow-example
```

Output must be a new directory with an existing parent. Every input is limited to 2 MiB;
at most 32 register files and 10,000 rows per list are allowed. Path components and files
cannot be symlinks; `..`, devices and FIFOs are rejected. Directory-descriptor-anchored I/O
prevents parent-symlink substitution during reads/writes. Files are created exclusively,
with mode 0600 in a 0700 directory; existing paths are never overwritten. Output failure
may leave a partial evidence directory; do not treat it as a complete result. The tool
is intended for a trusted local filesystem, not a hostile same-user process.

Exit 0 means projected measurements, not correctness or approval. Exit 2 means invalid
input or evidence-writing failure. Malformed but bounded readable bytes are retained;
unreadable/oversized files have explicit errors and no substituted empty data. For an
invalid run no observation or comparison is emitted; handled/transcribed counts are null
rather than guessed. Valid expected cases remain in `adapter-result.json` even if retained
input fails. CLI-level duplicate/invalid selection or output failure can stop before an
evidence directory exists.

## Evidence and measured utility

The new directory retains exact expected, selection and numbered register input bytes,
with their case/file bindings, lengths and SHA-256 checksums. It also contains:

- `adapter-result.json` (`nico.shadow-adapter-result.v1`): fixed boundaries, limitations,
  errors, complete expected cases, candidate-presence/missing-verdict/absent-ID lists,
  record and transcription counts. Retained aggregates never affect these counts.
- `observed.json`: comparator-consumable `nico.shadow-observed.v1` projection.
- `comparison.json`: unchanged comparator measurements plus fixed boundaries/limitations.
- `checksums.json`: hashes every other emitted file, including original inputs and outputs.

Outputs are deterministic for identical input bytes and ordered CLI selections. Keep
private input/output local and private; only these synthetic fixtures are publishable.
The synthetic example handles exactly three retained records and automatically copies
two verdicts (two per-candidate transcription steps removed), retaining one missing verdict,
one absent candidate and one missing case. Candidate coverage is 2/5; material omission is
4/5; the explicit zero case receives no complete-assessment credit. It does not estimate
hours saved or establish production calibration. Tests compare the generated observations
with a separately authored static observation fixture, and exercise malformed, foreign,
stale, duplicate, incomplete and unsafe-file cases. METRICS.md targets and all existing
golden assessment/approval/delivery checks remain unchanged.
