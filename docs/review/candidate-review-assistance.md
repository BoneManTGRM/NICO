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

Regression tests use synthetic nonsecret records. A separately retained authorized export has now been checked offline; its private bytes are not repository fixtures. Hosted CI and physical browser qualification remain separate. No percentage reduction, production speedup or completed investigation is claimed.

## Exact-run export handoff

For the current owner assessment, expected identity is run `comprun_0da8971c6ad81e7c7101e1192770658d`, repository `BoneManTGRM/NICO`, commit `67a60dd646a6d26bde2fa46cd157e3033450fbe7`. The authorized export was independently checked against this binding, its detached manifest and all eight artifact hashes and sizes.

Existing protected source paths are `/api/nico/assessment/comprehensive-run/{run_id}/localized-report/{en|es-MX}/evidence-package`. `localized_evidence_package` uses the same-run assembler, validates exact artifact hashes and returns a review ZIP with canonical JSON, detached manifest and artifact identity. `scripts/comprehensive_production_export_retention_v1.py` already documents the consumer checks. The path is documentation for the parent's authorized export; it does not authorize retrying denied access.

Retain the response's run/commit/report/language/canonical-truth/artifact SHA headers, ZIP bytes, member hashes and artifact identity. Verify `assessment_rerun=false` and pending human approval/client-delivery-blocked lifecycle. Match the canonical `identity` and `assessment.canonical_scanner_finding_register`, including record counts, `findings`, technical triage and `review_workload_clusters`. A PDF or Markdown summary alone cannot supply this register. An existing review-work projection additionally supplies current human dispositions, independent QC and open evidence requests; do not reconstruct a ledger from a report's count.

For each candidate, inventory identity, category/scanner/rule, occurrence count, source provider/repository/SHA/path/line, retained evidence quality, triage algorithm/version/status, supporting evidence/counterevidence/proof gaps and cluster membership. Missing fields remain missing. Keep private exports private and exclude raw credential values from reviewer summaries. Source locators alone are insufficient for new investigation: exact source bytes or trusted retained context and their binding must also be available. Do not mark the 1,675 UI count as 1,675 unique vulnerabilities or as an independently reconciled record count.

## Polling-status copy

Browser polling remains capped at 360 attempts with the same final exact-run reconciliation and manual same-run resume. Only `assessment_poll_budget_exhausted` uses “Automatic status checks paused” / “Consultas automáticas pausadas” in the issue and status badge. Genuine server timeouts retain their existing labels. No progress percentage, terminal status, timing, backend execution, acceptance or retry behavior changes.

## Offline source observation and report disclosures

`candidate_source_observations_v1` is a bounded offline helper, not a new production endpoint or automatic review action. Its caller must obtain a blob OID from a trusted exact-commit Git tree. It verifies the blob bytes, repository/path/commit binding and candidate line before describing Python AST structure. It never executes source or copies code, string literals or credential values. Repository/path metadata is retained for provenance. Unsupported rules, historical source mismatches and missing evidence remain unresolved. Structural matches are not findings of safety or exploitability; all recommendations still require human review.

The authorized 1,675-record export contained 1,583 Bandit, 24 OSV, 11 Gitleaks and 57 TruffleHog candidates. A bounded pass over 251 exact-commit source files observed expected structures at 1,229 candidate lines; 339 required unsupported rule semantics, 15 did not match the expected exact-line structure and 92 were outside that pass. None was dismissed, approved or used to change scores. Existing clustering already provided 687 groups; these are not newly achieved workload savings. The helper is not yet integrated as automatic live source investigation in the UI.

Final summary renderers disclose the complete canonical finding-register path and population, distinguish retained raw counts from confirmed material findings, and show SHA-matched consecutive-pass requirements separately from execution completion. Missing compact counts remain unavailable rather than becoming zero. Generated Spanish summary translations match only known authored statements. Explicit report locale remains independent of UI language.

## Bounded candidate investigation command

Run `python -m scripts.investigate_retained_candidates --canonical <authorized-canonical.json> --checkout <trusted-local-exact-source-checkout> --output <new-private-output.json>` using existing dependencies. The command neither fetches nor scans: it reads exact local Git objects with replacement objects, lazy fetching and transports disabled, rejects symlinks, limits each source file to 1 MiB and total source reads to 64 MiB, and creates the output exclusively. Preserve the original canonical export and keep the output private.

For B101, B404/B405 and B603/B607 it emits retained source references, rule-specific reasoning, counterevidence and reviewer questions. Assertions, imports and argument shapes are not vulnerability confirmations or false-positive dismissals. Multiple call expressions on one line remain unresolved. All packets retain human-required disposition, no score effect, and zero model calls. The public UI remains a retained-analysis queue; this offline investigation command is not yet a hosted background source-investigation service.

The authorized run's expanded pass produced bounded rule analysis for 1,177 of 1,675 candidates. The remaining 498 comprise 339 unsupported rule semantics, 63 historical source mismatches, 52 ambiguous call lines, 29 unsupported/missing exact-source cases and 15 source-line mismatches. Every candidate remains in the output and requires human disposition. These counts do not establish investigation of reachability or exploitability, or reductions in required review work.

## Why architecture and delivery capacity remain unscored

Historical commit `1bb4059c38cbe578fd6718c1a731576c0ef1b4dd` deliberately removed a default architecture score of 78 when measured input was absent. The current collector provides sampled complexity measurements, not a calibrated architecture score. Reintroducing that fallback or converting function-conformance percentages into architecture maturity would reverse the truth safeguard.

A numeric restoration requires a substantive versioned scoring contract: explicit construct and scope, justified calibration/weights, supported languages and coverage requirements, exact run/repository/customer/project/commit binding, uncertainty treatment and validation against representative reviewed cases. The existing 60% architecture / 40% immutable-CI calculation is a delivery-capacity proxy, not actual development velocity. Actual velocity needs time-bound delivery/outcome observations and its own defined measurement contract. No scoring or acceptance policy is changed by candidate assistance.

## In-product integration

New assessments capture bounded, text-free Python observations from the source text already acquired by the snapshot collector; they do not fetch source again. The capture explicitly identifies decoded snapshot text rather than claiming original Git byte identity. Scope binds run, repository, commit, customer and project. Capture permits at most 256 KiB per file, 8 MiB total input and 2 MiB retained observations, with a five-second cooperative deadline checked before and after each bounded parse. Candidate analysis uses a two-second cooperative budget and at most 10,000 analyzed records; remaining candidates stay unresolved.

The canonical scoring stage persists compact versioned investigation records alongside unchanged candidate findings. Existing review-work GETs only validate and display those records; they do not parse source or launch work. The bilingual panel shows coverage, source hash/path/line, rationale, counterevidence, reviewer questions and explicit unresolved reasons. No new endpoint, model/API call, disposition, score or approval action is added. Existing assessments without retained observations remain explicitly unavailable; their source is not silently reacquired or their historic artifacts rewritten.

Synthetic installed EN/ES final-report roundtrips verify all 1,675 investigation records survive final rendering and the review-work projection. This is integration qualification, not measured production coverage; the actual 1,177-record result above remains the separately authorized offline analysis.
