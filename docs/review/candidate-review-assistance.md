# Candidate review assistance

This increment adds a read-only assistance projection to the existing authorized review-work response and a bilingual paginated panel. It does not add an endpoint, scan, model call, disposition action, source fetch, approval or delivery authorization. It does not mutate stored assessments or scores.

## Existing capability

`candidate_technical_triage_v1` already produces deterministic proposals using retained evidence: affected dependency resolution, reachability, production scope, executable context, mitigation and boundary evidence. Unknown evidence remains unknown. `candidate_evidence_context_v1` binds scanner context and rejects ambiguous joins. Retained proposals are separately revalidated by `candidate_retained_triage_revalidation_v1`.

`candidate_phase1_workload_refinement_v1` groups normalized technical-review profiles. It retains member identities and distinguishes occurrence counts from candidate-record counts. Similar profiles do not prove identical source evidence. Existing review work requires authorized human dispositions, independent QC where applicable, resolution of high-impact escalations and evidence requests before final approval.

## Delivered increment

The assistant emits one packet per pending candidate record, ordered by high-impact risk, unresolved evidence, then supported retained nonblocking proposals. Completed human dispositions remain counted separately. Every packet binds its inputs with a SHA-256 digest. A GitHub source locator is emitted only with an explicit GitHub provider, matching exact source SHA, safe repository/path and optional positive integer line. Missing provider or source binding is reported, never guessed. A locator does not establish inspection or reachability.

Only fresh deterministic proposals with exact-source evidence, high confidence, no proof gaps, contradictions, changed evidence or existing individual-review requirement can be suggested for review as nonblocking. Confidence alone is never sufficient. Secret/high-impact candidates remain individual review. Failed, unknown and model-generated analysis cannot clear a candidate. Raw scanner payloads and arbitrary model/rationale text are not duplicated in the assistance packets. Existing protected candidate views retain the underlying evidence and rationale.

The UI shows 25 records per page without writes or source requests. It explicitly reports zero new source investigations/model calls. Every human decision still uses the existing authorized workflow. The assistant is navigation and prioritization, not a claim that each candidate was independently investigated.

## Next bounded investigation slice

Before claiming analysis of a specific run, obtain its canonical candidate register and retained exact-source evidence via an authorized existing export. Reconcile unique record counts, occurrence counts, category/rule breakdown and current clusters. Preserve the original export and source digest. Do not infer these values from aggregate UI counts or start another assessment.

Use source-bound, redacted evidence dossiers to investigate common rule families and split exceptions. Reuse analysis only when source/rule/evidence identity matches; shared cluster profile alone is insufficient. Each recommendation needs supporting evidence, counterevidence, explicit proof gaps, immutable source references and analyzer/version attribution. Count-only candidates remain unresolved. Never probe credentials or let source text act as instructions. Existing deterministic analysis can operate without paid services; broader model-backed investigation requires a separately established available model/runtime and budget, not an assumed free API.

Future qualification must exercise source mutations, ambiguous identities, cross-run leakage, false-positive dismissal hazards, grouped exceptions, missing source, model failure, unsafe source text and preservation of raw candidates, scores and human gates. Validate recommendations against specialist decisions before claiming workload savings.

## Verification limits

Local tests use synthetic nonsecret records. No live 1,675-candidate register has been inspected by this change. Hosted CI and physical browser qualification remain separate. No percentage reduction, production speedup or completed investigation is claimed.
