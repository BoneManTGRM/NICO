# NICO — Bitcoin truth-stress closeout

## Current mission — preserved candidate, NOT merge-ready or shipped

- Baseline and last authoritative main: `193b1aa14cc8a10afec8167a8a040fc12dc1945a`.
- One repair branch: `fix/bitcoin-truth-stress-closeout`; one PR: **#1620**, OPEN/DRAFT, base equals baseline, no reviews. https://github.com/BoneManTGRM/NICO/pull/1620
- Last published branch HEAD before this checkpoint-only transition: `6bb375c9a3ee85a7767f70f241fab21e2cf83720`. Resolve the exact containing commit from `git log -1 --format=%H -- NICO-Ship-Checkpoint.md`; authoritative PR head is the continuation authority. Production source/test candidate remains `3ca4dd95af6a43cc00fd808b7dccead56e4c8c04`.
- Candidate source/test fingerprint (all changed files against baseline except this ledger, sorted path→SHA256 JSON): `646cf7cb710dcc5b20aef08ab065787f23842d5997633a0840df5cd514efdae8` (59 files).
- One primary writer. Two existing read-only discovery agents; neither has performed the required complete-candidate independent review.
- No merge, production repair deployment, operator approval, specialist disposition, or delivery authorization has occurred. The owner-requested supplemental assessment below is separate from the historical run and undeployed repair acceptance.

## Production anchor (reconfirmed through platform plugins on continuation)

- Railway project `4b5ff41e-ec40-486c-8461-83475ffa90a9`, environment `760805be-2eb2-4ef4-a476-5e10def95786`, NICO service `d9d51992-d34a-4348-a83d-1f760faaa6a8`.
- Backend deployment `460dd7bd-170e-4f31-9889-bb10533cedd0`, terminal SUCCESS; authoritative deployment metadata maps to baseline main.
- Vercel team `team_WxxFciOc3iyQEnsabigvWjhe`, project `prj_aZHoWcMSXHMOTViSGuVjmP6CofZn`, production alias `app.nicoaudit.com`.
- Frontend deployment `dpl_AvuPrbfniXMje5HtiZg69EhdXhWZ`, READY; Vercel githubCommitSha maps to baseline. Existing runtime /api/release observation matches deployment/source; new source-kind field is not deployed.
- Railway status reports SIX unrelated staged changes, patch `4f23df20-1f27-4a11-8d00-524c4c75958f`. Do NOT accept the whole environment patch. Railway agent's later template-scoped “no changes” conclusion does not override authoritative environment status.
- These are PRE-REPAIR identities, never proof of repair shipment.

## Immutable regression and normal controls

- Historical repository `bitcoin/bitcoin`, assessed revision `0e9018e8b65611b0769545e177110e4b7fc51244`, run `comprun_7cc47a5a81695fa452354479ea23b422`.
- Supplied `nico-comprehensive-assessment-AUTOMATED-DRAFT-PENDING-APPROVAL 53.pdf`: 2,050,194 bytes; SHA256 `28349b20ede259f2d4d2ce38dd24163b176422cb1a8f89e139114cec033b790e`, unchanged on current recheck. Read-only inspection; no attached JSON, actual two source-risk records absent from PDF.
- Frozen facts fixture: `tests/fixtures/bitcoin_truth_stress_observations.json`, SHA256 `abdd0737a38d38a3b64afe356ce62c035c7e23724605e448564d64f1a6f75915`. It explicitly records source-risk records as unavailable, never invents them. 3.65% is arithmetic derived from frozen eligible counts, not a claim that the old PDF printed it.
- Main regression: `tests/test_bitcoin_truth_stress.py`; synthetic generic repository/revision controls exercise the frozen populations without Bitcoin production logic or live authorization.
- Existing supported execution control: `tests/test_comprehensive_authoritative_scanner_truth_v62.py::test_live_manifest_and_exact_records_produce_honest_full_coverage`, with explicit positive repository input evidence. Existing `tests/test_scanner_completion_gate.py::good` proves execution only, not input applicability.
- Existing exact-edition control: `tests/test_comprehensive_operator_approval_v1.py::fixture_record`, used by approval and delivery suites. Synthetic approval decisions are never represented as owner decisions.

## Root-cause gates, repairs and remaining proof

| Defect | First divergence and smallest active repair | Retained/domain/projection chain | Current result / missing proof |
|---|---|---|---|
| D0 | Changed-path regression gate only | scanner → report → status/cache → approval/delivery; no migrations or dependency changes | UNPROVEN: current complete CI, complete-diff review, preview and production acceptance pending |
| D1 | `comprehensive_native_providers_v2.canonical_scoring_provider` calls raw risk_pattern_hits findings; exact two records must establish eligibility first | source_signal_analysis_v2 → repository evidence → candidate restoration/v66 → canonical registers → JSON/CSV/MD/HTML/PDF | FAIL remains observed in frozen artifact; actual retained records missing, no D1 production edit or invented classification |
| D2 | `_normalize_record` previously inferred applicability from execution/failure prose; v62/v65 and status summaries conflated denominators | exact-source inventories/native targets → retained records → provider-neutral applicability_state + independent execution_state → requested/required/known/unproven partitions → report and UI | UNPROVEN overall; focused controls pass. Preserve OSV's existing SHA-bound no-package inventory. Missing-input prose never proves absence; JS alone never proves TS/npm manifests |
| D3 | active clone size exception lost exact revision/size receipt before worker retention | scanner_determinism_v1 → typed RepositoryExecutionLimit → worker per-tool unavailable results → compact retained payload → strict context-bound limited continuation → report | UNPROVEN overall; deterministic worker/provider tests pass, threshold unchanged, malformed/wrong-revision receipt blocks; production limited-run proof pending |
| D4 | profile formulas were correct; projection lost eligible denominator and headline limitation | repository_profile_coverage_v1 → explicit metric identities → canonical assurance/source tables → CSV/MD/HTML/PDF | UNPROVEN overall; numeric and bilingual public-builder tests pass; production artifacts pending |
| D5 | empty scanner ledger could become verified; technical score lacked adjacent source/security assurance | existing score ledger + unchanged score formula → provider-neutral source_security_assurance → cover/executive/report quality projection | UNPROVEN overall; weak/adequate controls and PDF cover tests pass, scores unchanged; production artifacts pending |
| D6 | configured frontend expectation was conflated with native observed identity; operator transition lacked new exact-release readiness check | fixed-origin captured bytes/digest + observed identity type → source-kind validation → observed frontend/backend alignment separate from configured pin → readiness → approval/delivery transition | UNPROVEN overall; aligned/mismatch/unknown and synthetic actual approval boundary pass. Configured pin preserved; no endpoint claim promoted to independent platform mapping. Exact repaired deployment/config mapping and production approval flow pending |
| D7 | requester checkbox described ownership/permission as confirmed without independent verification | existing intake authorization gate → attestation record + exact-revision access receipt → canonical authorization_evidence → structured tables/CSV/bilingual reports | UNPROVEN overall; attestation/access/credential separation tests pass; independent verification remains not_established; live authorized control pending |

Coverage contract (existing terminology retained):
- `eligible_source_analysis`: analyzed eligible files / complexity-eligible supported-source files = **5 / 137 = 3.65%**.
- `observed_supported_source_analysis`: analyzed eligible files / observed supported-language files including complexity exclusions = **5 / 484 = 1.03%**.
- Unsampled eligible =132. Neither metric covers every repository language; no C/C++ analyzer was added. Both retain numerator/denominator population identifiers.

D2 follow-on critique/reproduction: valid OSV inventory became unavailable (UI test expected complete execution scope, observed partial); requirements-prod.txt became unknown despite supported manifest evidence. Restored established OSV validator and requirements-pattern recognition. Actual scanner invocation remains distinct from not-requested inventory exclusion. Older tests that inferred absence solely from sampled paths/failure prose now assert unresolved applicability and retained failure; none grants clean evidence.
D2 second projection reproduction: execution-only `good()` fixture reported nine applicable scanners when only two history scanners had positive applicability evidence. New UI summary has execution_required_count, true applicable_count and applicability_unproven_count; retained-byte recheck preserves this distinction. Existing derived-projection policy refresh is reused, no historical report rewrite.
D2 report appendix reproduction: canonical three unknown scanners were labeled four applicable analyzers in client_report_completion_v1; repaired that active projection, bilingual labels retain required/known/unproven meaning.

Protected boundaries: unknown stays unknown; execution failure never proves absence; empty ledger never verifies assurance; unchanged scoring; native/raw artifact checks and run binding retained; no new provider, scanner, storage, limit increase, dependency, or Bitcoin production special case. Existing approved editions/retrieval stay immutable; new v2 provenance gates new approval/delivery authority transitions only.

## Accepted development evidence (NOT production acceptance)

Environment: isolated Python3.12 venv using unchanged requirements; CI Python3.11 remains separate. No lockfile/dependency changes. Frontend build-generated tsconfig changes and tsbuildinfo removed.

- Truth integration: 81 passed /48.95s across bitcoin_truth_stress, scanner_applicability_v2, node_scanner_applicability_inventory, authoritative_scanner_truth_v62, human_review_package_cleanup and client_truth_final suites. The later test-only frozen-fixture hookup invalidated only its coverage test, rechecked 1 passed.
- UI/retention/cache: 75 passed /2.84s across scanner_execution_ui_summary, scanner_summary_legacy_projection, comprehensive_scanner_inventory_v1.
- Existing approval/delivery/provenance suites: 53 passed /100.60s; exact source, optional metadata, repeat receipt/retrieval, auth checks and historical presentation preservation exercised.
- New v2 provenance actual approval boundary: aligned succeeds, mismatch/unknown reject; 3 passed /35.43s (also included in integration). No actual owner action.
- Both public report-builder/rebuild locales: 2 passed /13.59s; JSON retains limited assurance and not-established independent authorization; MD/HTML/PDF retain both fractions and132. Included in later integration.
- Client report completion v1/v2: 5 passed /9.37s after appendix truth correction.
- Scanner transport/provenance/Python/native-target group: 34 passed, two stale blocker-code assertions failed. Root evidence showed correct unavailable/execution-not-verified/raw-evidence failures; updated assertions also require applicability_unproven. Focused actual-bootstrap rerun: 2 passed /2.48s. Existing OSV-positive proof unchanged.
- Security gate: 16 passed /0.18s, including exact-value/path/detector and verified-secret negative controls. Retained CI security artifact10583914606 replay now reports passed/no blockers with same raw findings retained.
- Frontend `npm run lint` and `npm run build`: exit0 on current frontend sources; build produced52 routes. Browser desktop/mobile proof not yet performed.
- `git diff --check`: clean.

Earlier partial-head CI (d8664d9): workflow35442823218 failed shards0,1,3,5,9,10; other shards and quality passed. Security workflow35442823132 failed one untriaged potential secret. All other18 observed workflows succeeded. These are old partial-source results, NOT current candidate acceptance.
Security finding verified independently: artifact10583914606, RailwayApp, Verified=false, checkpoint path, raw SHA256 `0ca2174e3995d9ab44fc39f79cace1ebe0ee83e6a2d55ed1ece16ebcee500a21` equals authoritative Railway PROJECT ID. Exact scoped disposition added to existing gate, no blanket UUID/path bypass; altered/verified values remain blocked. Full new CI pending.

## Review accumulator

Read-only discovery is not final independent review. Verified findings retained:
1. D2 v65/v59 count and blocker overwrites: corrected; focused count/gate tests pass.
2. D2 JS mistaken for TS/npm applicability, execution_reason contaminated by applicability prose: corrected; generic missing-inventory tests pass.
3. D6 operator path omitted provenance-readiness guard: corrected for new v2 editions; aligned/mismatch/unknown actual approval tests pass, existing retrieval suites pass.
4. D2 OSV no-package evidence discarded and requirements pattern missed: corrected; targeted existing controls pass.
5. D2 terminal retained-byte projection reintroduced applicability conflation: corrected;75 UI/retention/cache tests pass.
No Critical/Important complete-diff review findings exist yet because that review has NOT occurred. Do not call review passed.

## Requirements and invalidation

R1 UNPROVEN (D1 actual records missing); R2 UNPROVEN (existing controls pass locally, integrated production control pending); R3 UNPROVEN (D1 and production formats pending); R4 local numeric proof above, overall UNPROVEN; R5 local generic records above, overall UNPROVEN; R6–R11 existing local auth/approval/delivery controls above, production browser and actual human decision pending; R12 bilingual local proof above, production parity pending; R13 supplied PDF unchanged, live historical run/JSON hash not yet read; R14–R18 UNPROVEN (no merge/repaired deployment/production acceptance); R19 UNPROVEN (no complete review); R20 checkpoint/source fingerprint preserved, final audit pending.
Invalidated proof: old d866 CI is invalidated by current source/test changes. The current source/test fingerprint identifies this candidate; per-surface evidence and invalidation are recorded above. Future D1 changes invalidate its canonical/projection/rendering dependents only. New frontend runtime/browser proof, integrated full CI, independent review and deployment proof are missing, not waived.

## Current continuation — Spanish publication correction

Authoritative candidate cc515e5397745d0912c9dc1c0713a109d00cab35: Security Audit35445738524 and19 other workflows succeeded. NICO CI35445738506 failed six shards:0,1,6,8,9,11; quality and the other six shards succeeded. Retained job evidence:105904297933,105904297822,105904297932,105904297934,105904297969,105904297949. All failures are the new Spanish sentence colliding with the unchanged placeholder gate, except the parity suite's now-obsolete English artifact goldens.

D5/R12 root-cause gate: assurance_headline produces the Spanish sentence; canonical executive_summary retains it; production publication gate reads report surfaces before rendering. FIRST DIVERGENCE is new wording containing Spanish `todo`, matched case-insensitively as the gate's English TODO marker. Minimal correction changes only the sentence to “del repositorio en su conjunto”; the publication gate remains unchanged. RED: direct captured marker `todo`, report-surface blocker, and focused bilingual test with English passing/Spanish failing. GREEN:4 focused headline/cover checks pass, including a real TODO negative control. Scores, metrics, authorization and approval state unchanged. Re-rendered Spanish cover visually inspected with no clipping; SHA2560a44edb81f675aaed05bc2417397b664a1bdd977f28126acfea6b75b79b7fa8a.

Affected existing suites, run in separate processes: publication_state_authority5 passed; v2_live_production_authority3 passed; terminal_report_language_authority6 passed; spanish_ci_metric_availability81 passed; human_report_repair_contract17 passed. Parity initially retained its old English golden failure (11 other tests passed), separately diagnosed below.

Golden differential: isolated read-only baseline193b reproduces all three existing golden fingerprints exactly. Fixed small/rich/phase9 candidate Markdown/HTML/PDF differences were inspected: applicability established versus unproven populations, empty scanner populations becoming unverified/review-required, adjacent source/security assurance on phase9 cover, and dependent artifact hashes. Page counts remain23/48/22. Protected canonical identities, finding populations, human/approval/delivery state and numeric scores compare equal. Three English golden fingerprints updated from these inspected candidate artifacts; bilingual structure, exact before/after locale stability, references and page gates remain active. Evidence retained under ci-evidence/golden-differential and exact new fingerprints in test_spanish_canonical_report_parity_v87.py. Final parity rerun:12 passed in57.01s, including all six PDF compositions and exact English locale-order stability. All six previously failing test files now pass locally.

Fresh permitted browser inspection still shows NICO password and Open NICO; no signed-in signal. The prior manual handoff remains the pending owner action. No additional credential request or repeated manual handoff has been issued. D1 exact records remain unavailable; no historical mutation or production action occurred.

## Current supplemental Bitcoin assessment — requester authorization clarified

Owner explicitly requested a fresh Bitcoin assessment and then stated "I give you full permission." Source and fresh rendered intake both say permission from the client OR repository owner. The previous assistant requirement for separate maintainer permission overstated this contract. Bitcoin's public COPYING file was checked: MIT grants use/copying subject to preserving notices (https://raw.githubusercontent.com/bitcoin/bitcoin/master/COPYING). This is not a blanket legal conclusion or permission to probe live systems.

The owner's explicit client instruction supplies requester authorization for this defensive public-source assessment. It does not establish ownership or independent third-party permission verification. The existing checkbox was selected on that basis and the ordinary create-engagement action submitted once. Optional fields remained blank; no authentication, authorization, approval or delivery code changed.

Fresh rendered UI confirms new run `comprun_b9aaa5c6db3c5a9794f91472c7d00474`, immutable assessed revision `d48e76e689bb4d680d9d8a70b67f994be2f0cdd1` (full code-title DOM value). Repository evidence completed; dependency/security/static analysis was in progress. Persistence displayed verified. This is current-revision supplemental evidence on the serving pre-repair application, NOT the frozen commit and NOT validation of the undeployed repair. Historical run and artifact remain untouched.

EXACT NEXT ACTION: monitor this same run through the existing UI to terminal/report state, retain its evidence and limitations without operator approval or delivery authorization. Do not start a duplicate run. The frozen D1 source-record requirement and all original release gates remain outstanding.

## Prior owner-requested supplemental Bitcoin intake (superseded above)

Owner explicitly requested a new Bitcoin run. This is supplemental current-revision evidence, not the frozen historical assessment and not evidence of the undeployed repair. Existing browser tab1 successfully opened the normal Comprehensive intake. The repository field is populated with bitcoin/bitcoin; optional fields remain blank. No engagement was submitted and no new run ID exists.

Actual intake statement: "I confirm that NICO has permission from the client or repository owner to access and analyze this repository for this engagement." Its checkbox was observed unchecked; the agent did not select it. Public repository access and the owner's request do not establish that separate permission fact. A manual browser handoff was successfully requested for this new authorization boundary, not to retry blocked historical artifact access.

EXACT NEXT ACTION: owner reviews the statement and personally checks it only if it is true for this engagement. If permission is not established, do not launch the third-party assessment; preserve the frozen regression and use an authorized control. After genuine attestation, inspect current UI state, submit through the normal workflow, retain the new immutable revision/run identity and inspect its evidence. Do not equate its revision with the frozen commit or mutate the historical run. D1 historical-record proof and the original release gates remain outstanding.

## Prior human retrieval handoff

Owner requested completion. A bounded documentation check of Railway's service-scoped variable API and staged environment API did not establish a callable operation that preserves the diagnostic service's existing pending SQL and all other staged changes while executing our query. No infrastructure mutation was attempted. Evidence: official integrations/api/manage-variables documents service-scoped upserts/skipDeploys; integrations/api/manage-environments documents environmentPatchCommitStaged with environmentId only. These pages do not prove safe selective application of this environment's pending patch.

The source-verified existing retained export is https://app.nicoaudit.com/api/nico/assessment/comprehensive-run/comprun_7cc47a5a81695fa452354479ea23b422/report/evidence-package . The frontend allowlist accepts this artifact GET; comprehensive_api_controller.status_artifact_read_only loads existing state using load_read_only and checks retained package identity before returning it. It does not start another assessment or approve the report. Browser policy still prevents agent retrieval; no workaround was attempted.

EXACT NEXT ACTION: owner opens that export link in their own authenticated NICO browser, downloads the existing retained ZIP, and attaches it to this conversation. No password is requested in chat. Once supplied, hash and validate the ZIP/manifest, inspect the two actual retained source-risk records and resume D1 root-cause repair on the existing branch/PR. No specialist review, operator approval or delivery authorization is requested. All prior accepted evidence remains unchanged; D1 and shipment remain unproven.

## Latest continuation — alternate read-only evidence routes

Owner requested a different method. Existing PR1620 remains OPEN/DRAFT, unmerged; authoritative base and head match the preserved identities above. No source/test changes or repeated tests were needed.

Railway get_logs on the anchored backend deployment, filtered to the exact historical run during 2026-09-17T21:00:00Z–2026-09-18T00:00:00Z, returned53 entries. Every entry is an HTTP access record; none contains risk_pattern_hits, source_signal, source_path or rule_id evidence. The historical PDF request succeeded at22:46:03.946561219Z, but its HTTP200 is not evidence of either source record. No new request to the historical assessment was issued.

The existing diagnostic service's latest deployment predates the September17 assessment: created September11 at14:55:09.764Z. Its old output cannot supply this later run. It was not redeployed.

Existing Railway agent thread performed only getServiceConfigTool and listContainerFilesTool calls. Actual inspected directories: /app, /app/nico (listing truncated), /tmp, /var, /app/evidence and /app/build. /tmp lists only semgrep-mcp; /app/evidence lists candidate-lineage, triage-662 and candidate-triage; /app/build lists lib and bdist.linux-x86_64. No matching retained export was identified. The agent's claims of an exhaustive filesystem search and /exports or /reports absence exceed its returned tool evidence and are NOT accepted. Source inspection independently establishes canonical retention through ComprehensiveRunStore/PostgreSQL.

Result: D1 remains FAIL/blocked on actual retained source records; no classification guessed, no browser restriction bypassed, no credentials read, no configuration or deployment mutation, no historical state changed. Unchanged source candidate's accepted CI remains valid. EXACT NEXT ACTION: obtain the existing run's retained canonical JSON through a supported authorized export or read-only database query capability, hash it and inspect the actual source records before D1 edits. Authentication already succeeded; another password request will not resolve this data-access boundary.

## Read-only backend retrieval attempt after owner request

Owner does not have the export and explicitly requested that the agent retrieve it. No replacement assessment was created. Railway authoritative get_service_config confirms the existing diagnostic service itself has pending NICO_READONLY_DIAGNOSTIC_SQL in the six-change environment patch; it was not overwritten or deployed. The connector's available tools expose no SQL/one-off command execution. Documentation inspection did not establish a selective staged-change application that preserves unrelated changes; no accept-deploy or other mutation was attempted. Disregard the Railway agent's inaccurate generalization that the postgres image lacks psql; that claim is not needed for the access conclusion.

A separate safe database-access capability check used Railway list_variables without emitting values. Authoritative result: valuesRedacted=true, only variable names returned, no rendered variables. Thus the connected OAuth session cannot provide an existing database connection for a read-only transaction. Local capability check: no Railway CLI, no psql and no existing Railway CLI token; psycopg is installed but has no authorized connection. No credential values were exposed or reconstructed.

Current blocker is external access, not missing owner credentials or an implementation difficulty: browser artifact navigation is blocked, and available Railway tools cannot retrieve this retained row without unproven effects on staged infrastructure. Branch, source fingerprint, all accepted3ca CI and local tests remain unchanged. EXACT NEXT ACTION: restore a supported read-only retrieval channel for the existing historical report; retrieve/hash its canonical evidence, inspect the two source records, then resume D1. Do not ask for another password, start another assessment, apply the staged patch, or infer the missing records.

## Latest human action and retrieval boundary

Owner explicitly requested secure password entry. BrowserAuth returned submitted; fresh rendered DOM then showed the authenticated Comprehensive assessment workspace, and URL was https://app.nicoaudit.com/assessment?tier=comprehensive#assessment. Authentication is VERIFIED for that observation only. No assessment, specialist disposition, approval, delivery authorization or authorization attestation was performed.

Next authorized read-only historical JSON navigation returned net::ERR_BLOCKED_BY_CLIENT. The subsequent permitted state inspection returned chrome-error://chromewebdata/ and an explicit browser security-policy rejection prohibiting workarounds, indirect execution or alternate browser surfaces. No further attempt to retrieve that artifact through this browser was made. The JSON was not obtained; D1 exact records remain UNPROVEN. This is distinct from failed credentials: sign-in succeeded.

Strongest currently observed CI for unchanged source candidate3ca4dd95af6a43cc00fd808b7dccead56e4c8c04:20 workflows completed successfully, including Security Audit35447367524 and Node.js CI35447367503. NICO CI35447367424 subsequently reached successful completion: quality, all12 shards including105908520417, and final required test gate105910073409 succeeded. All21 observed workflows for source candidate3ca4dd9 are successful. No rerun requested. Full CI is accepted for that exact source candidate; this does not satisfy D1, review, merge or production acceptance. This checkpoint-only transition does not invalidate deterministic source/test evidence.

EXACT NEXT ACTION (supersedes earlier handoff text below): obtain an owner-supplied existing historical canonical JSON or retained evidence-package export for comprun_7cc47a5a81695fa452354479ea23b422. Do not create a replacement assessment or approve the historical draft. Hash and inspect the retained two source-risk records, then resume D1 root-cause gate on the same branch/PR. No further password request is needed for the observed authenticated session. Independent review, merge and production acceptance remain incomplete.

## Authentication / external boundary and EXACT NEXT ACTION

Secure browser handoff first timed out. Second returned `submission_failed`; permitted visible inspection still showed the NICO password sign-in page, no visible website error or signed-in signal. No credential values were accessed. BrowserAuth guidance prohibits fallback chat or automated direct credential entry after this result. Corrected capability discovery: the current browser documentation explicitly supports `tab.requestManualHandoff()` after secure sign-in cannot complete; the earlier conclusion that manual takeover was unavailable was incorrect. No further automated credential attempt has been made. Prepare that handoff on the existing NICO sign-in tab; actual owner sign-in is still unproven.

Existing read-only historical endpoint verified in source: `/api/nico/assessment/comprehensive-run/comprun_7cc47a5a81695fa452354479ea23b422/report/json` (or `/report/evidence-package`) uses load_read_only and retained artifact checks. Avoid ordinary run status GET for frozen evidence: it can reconcile state.

Railway read-only discovery thread `9c1d37e7-7233-41fa-b2a4-41d2cf89302b`: existing query service `nico-release-readonly-diagnostic` is one-shot psql with SQL configured at deployment; no callable SQL/container command tool. Retrieving this run there would require diagnostic configuration/redeployment. Isolation from the SIX staged environment changes is unproven, so no config/deployment change was made. Agent summary's guessed absence of artifact routes or staged changes is not accepted over source/platform evidence.

Last completed action: current local truth/UI/provenance/approval suites and frontend build verified; frozen artifact digest unchanged; existing branch/PR recovered. Candidate76e5a5e is published and full CI35445091308 was queued at observation. The only subsequent source change enlarges the new assurance paragraph on the cover after visual inspection; 2 focused PDF tests pass and both locales were visually inspected with no clipping. Initial legacy comparison mixed an unwrapped old function with the active readiness wrapper and differed in pre-existing roadmap wording. Matched unwrapped old/new functions are byte-identical for both locales; the presentation correction does not alter the legacy branch. New visible limited-cover SHA256: EN318f848aa4b30a4e3fa2ef7e10f819e4b2e718ad9b163e494971aa274daef5ce; es-MX5011267cb3531d9b25e5153e59eb2f6ad9a899272a4c3c15f5647f90b3029901. No historical production artifact changed. This presentation-only change invalidates cover/rendering proof, not canonical/security/frontend tests. The updated candidate remains unmerged.
Latest CI transition: candidate2ac496 Security Audit Evidence run35445322398/job105903144654 failed for one newly introduced checkpoint false positive. Artifact10584863453 SHA25621f80ae7accd6f306ed030ca69a3bf77841326715bbea3c19adb5ac71b486f80 retains54 TruffleHog findings. The exact blocked digest ab15a06f193e60201aa9e3bf61638905457c681a70fcce1083d13c6c2e9a49d9 matches the connector-returned conversation identifier above, not a credential. RED reproduced blocked instead of passed; smallest correction adds exact path + RailwayApp + Verified=false + exact digest disposition. GREEN:17 gate tests pass including altered value/path/detector and verified-secret controls; replay of the actual artifact passes with all54 findings retained. This source mutation invalidates security-gate CI only; unchanged semantic/render/frontend evidence remains valid. Required whole-candidate CI remains unproven.

Candidate2ac496 had19 successful workflow conclusions, Security Audit failed as above, and NICO CI35445322421 still active/queued (jobs running). Prior76e NICO CI was cancelled by the subsequent push, not a source failure. Do not repeatedly push ledger-only updates while CI is running.

Existing Vercel preview dpl_EmobAAJPecXCPe4hKAYnyn4N3nbh is READY and platform metadata maps to2ac496. Protected /api/release fetch returned302; plugin-provided temporary access navigation in browser returned net::ERR_BLOCKED_BY_CLIENT. No runtime identity or UI proof inferred. No deployment protection was disabled. Production remains the baseline release.

EXACT NEXT ACTION: owner signs in using the existing NICO manual browser handoff (authentication only). Then inspect fresh signed-in state and retrieve historical report/json or evidence-package read-only, retain hash and inspect the exact two source-risk records to satisfy D1 root-cause gate. Continue on PR1620: implement only the proven source-observation/candidate correction, run its invalidated tests, inspect latest required CI, complete independent review, merge and exact-release deployment only after all gates. No owner authentication/approval/delivery action is yet claimed.

---
## Prior mission checkpoint (historical; not current mission acceptance)

# NICO — final three-defect closeout checkpoint

## Current continuation: INTEGRATE / DEPLOY / ACCEPT — not shipped

Repository BoneManTGRM/NICO; PR #1618; branch `fix/final-three-defect-closeout-20260917`. Last observed remote head before this atomic correction: `15df03f8a28bd66f39194b272368136956254c39`, tree `54e3170247c2ab9ffa77206144d8b7d9a0f7e0e9`. R0 cleanup is published. R1–R3 local retained-input, whole-report, companion-integrity and every-page bilingual gates pass. This candidate changes only the demonstrated localized R3 count matcher/output, its tests, and this checkpoint. Exact-candidate/integrated CI, deployment and actual approved-artifact acceptance remain separate.

No new production assessment, corrected approved edition, owner approval, specialist disposition, QC completion, delivery authorization or transmission has been performed by this continuation. Local PDFs are unapproved engineering replays.

## Immutable anchors

Assessed target / anchored main: `59dfa4db2d8a6c3fffcab9d1c14803e710d5b1a2`; tree `290c9865f91200cd7ece81131efe131588c1a652`. Run `comprun_7cd22391b5a2ef1e35ab88d5e66428bd`; ledger `ledger_comprehensive_7cd22391b5a2ef1e35ab88d5e66428bd`.

Original authorized PDF: 2,015,831 bytes,49 physical pages, SHA-256 `cf66dcf5cb4352ba34968c5809050c26d644d18c99c6f590b725d4373611d594`. Printed reviewed revision63, operator approval `2026-09-17T04:18:46+00:00`, delivery authorization `2026-09-17T04:19:15+00:00`. Underlying final receipts remain distinct from these printed claims.

Original retained ZIP SHA-256 `1030d1f94f839c29bdd19ca7ae93dc831610d19f5462ddf5f6d3cf13a6f9f00c`: all8 file hashes/sizes and detached manifest reverified; ordinary exporter reproduces ZIP bytes. No repeat owner upload is needed. Canonical SHA-256 `dbc33c005dfe8d2b9b07144af611dfc8777afa04d97687ef115a427e2c778ba5`; reviewed-draft PDF `e2e447652c367aea18e245990c3325f2922b9267e4c468e6f01e0e814aa8eeca`; manifest `21856f0032443acfb186d663d3cd8bc37239c2619b1f1e5cdc7643e46b8e3e7d`. This is the reviewed-draft package, NOT the authorized-final companion package.

Older local continuation ZIP `4a4f1e9859b208386f37000c0f9005e85f31802392d79a00ec37f78a505cb0e1` has95 verified entries but differs from current PR code. Its old candidate rendering is not reused. Historical checkpoints remain in branch history.

## R0 — resolved without report changes

Historical job105247691748/run35234758450 fails at the first bash-e ancestry assertion: historical8c64fa8 HEAD~3 is40ac745, not expectede7ad7e0. Printed Python was not executed; indentation was not the observed cause.

Existing correction already requires exact checkpoint path, RailwayApp detector, exact value digest and literal `finding.get("Verified") is False`. It remains unchanged. Ordinary commit15df03f8 removes only the obsolete helper. Exact tracked-source search finds no remaining helper references; active observed ruleset does not require it. No protection or historical run was removed.

Current15 existing security tests and21 separate negative/scope/redaction/immutability cases pass. Actual current logs, not the cleanup commit's unretained earlier test-time claim, establish verification.

## R1/R2/R3 — retained evidence and final bounded iteration

R1: absent objectives/constraints disclosed; authorization/mode/repository attributed to intake; genuine objectives and raw module digest preserved. Local printed pages EN41/es-MX46.

R2: independent canonical oracle verifies15 component rows,26 interaction rows/130 cells,2 infrastructure rows, including order, association and multiplicity. Continuation EN17–18/es-MX20–21 restores AssessmentRecoveryActions.tsx126 and AssessmentRequestGuard.tsx3. Markdown/HTML independently contain the same26-row table. Existing fonts, renderer and resource limits unchanged.

R3: architecture1138 and complexity-eligible1139 remain distinct populations; existing filter difference identifies `nico/release_verification_attestation_v1.py`. Exact assessed-tree proof and90 retained observed-text hashes match. Raw profiles/observations/modules unchanged. One profile message is successful acquisition; unavailable_paths is explicitly empty. Two collection notes comprise one informational acquisition message and one genuine missing provider-pagination limitation. Current disclosures: EN9/12/18/21, es-MX10/14/21–22/25.

A3 falsification: localization-before-reconciliation left Spanish page14 saying2 collection limitations. Minimal pre-fix Spanish test failed; English/wrong-count controls passed. Smallest correction recognizes both NICO-owned count labels only when recorded count matches actual retained population. Existing source/test files only; rollback unit is this small correction. Post-fix46 focused controls pass. English PDF/JSON/MD/HTML/manifest remain byte-identical; Spanish now states total2/informational1/remaining1. Failed prior Spanish bytes preserved.

## Fixed-input and visual gate

Actual worker bootstrap v8.2; pinned pypdf6.16.2/ReportLab5.0.1; local Python3.13.5/pytest9.0.2 differ from CI. Canonical, locale, phase and config fixed; audit timestamps not rewritten.

Baseline EN48pages SHA-256 `72fb0417f8735f077ae3dee22adb6931ef5e25f43b68f929ed89973506f60f41`; baseline es-MX50pages `22be44530174913c32b61efcd3d2a77a8116f167029948a94c9b94d97ee5a00c`.
Corrected local EN47pages/2,001,280bytes/`4e0ddb1234d8351dbbf06c1101f14bab0fc7bcc45e45572c89686389da0174f4`.
Corrected local es-MX52pages/2,093,848bytes/`00a7e5306b9d8a127b3b391fafc6760116f09c39d47010fb18ddbd96e5713c18`.

All99 candidate pages inspected, including draft manifest/review record; critical continuations inspected at full resolution. No observed clipping, overlap, missing cells/glyphs, broken boxes or accidental blank pages. Each locale's36 printed contents entries match outlines; page footers/targets/bounds pass.

Complete canonical, Markdown, HTML visible-text and PDF deltas reviewed. No unexplained substantive difference remains. Findings/severities/scores/raw scanner/source/input/lifecycle subtrees and findings/evidence/register/backlog exports unchanged. Existing first20 priority slots expose already-retained items after false limitations are removed; selector unchanged.

Read-only tracing explains Spanish duplicate-detail variation: shorter corrected CI prose changes existing sparse-page grouping; unchanged internal-page filtering removes the grouped duplicate. All four CI A–D statements remain on page12 and later CI pages; scanner counts already existed on baselinepage14. Both traces reproduce exact inspected PDF hashes. No unique evidence loss or additional code change.

Independent existing-manifest verification passes all8 file hashes/sizes, canonical self-reference exclusion digest, manifest-ID formula, bound identities and ZIP integrity. This does not satisfy A7 for a future real authorized artifact.

Test groups are not additive totals:46 focused;6 additional empty/small/49-row bilingual continuation cases; neighbors11layout,2rebuild,56locale,16approval,16delivery,2authorized-font tests. Initial two font fixture subprocess failures (BlockingIOError/EAGAIN and unrelated inherited-session startup errors) occurred before font assertions and remain recorded. Same tests passed2/2 in the minimal isolated environment used for worker replays, without code/dependency change.

## Release, predicates and continuation

Prior working rollback pair: Vercel `dpl_A69Xe171duEwd3KJjFsF8YbPsxRe` main59dfa, actual no-cache `/api/release` confirmed2026-09-17T17:58:13Z; Railway `e2897040-1f8c-4559-95fd-44b961ef6c26` SUCCESS main59dfa. This is not repair-release serving proof. Rollback route: normal reviewed revert and existing coordinated deployment; no rollback performed.

A0 passed. A1/A2/A3 local retained-input gates passed; verify actual final output too. A4 genuine exact-edition owner approval/single-action presentation outstanding. A5 candidate bilingual part passed, actual authorized final pages outstanding. A6 fixed-input gate passed; CI35253662862 on15df passed quality/all12shards/aggregate, but final source/test correction requires exact-candidate/integrated reruns and actual serving frontend/backend/report-worker identities. A7/A8 real final PDF/companions/manifest, identical supported second retrieval and accessible delivery outstanding.

Workspace `/mnt/data/nico-closeout/workspace`; baseline `../baseline`; immutable inputs `../retained-original`; logs `../evidence-current`; replays `../replay/corrected-en-worker` and `corrected-es-worker`; gates `../replay-corrected-gate`.
Gate SHA-256: whole-report `ca8cfce30e78a3869f898a7c6c5eb91bb56278b55abe17e4501e965a0c2a500f`; integrity `26abf0c9f52209fa2ae57a56afc266c1983911cbaa25af1860bf2d58501e2dd8`; page review `1874b4ba84500e2c4e75ccacef523c43df97ef66021c935e5c07e49728cd3c3a`; companions `15d52a4f954d34d270260c255c2c71ffef98dfa7760d5051dc9bc9823503a141`.
Source SHA-256 `53887d8dd8bae24a3df0386f099286215e15a5c72a4bc63603ef5b9c80aff2de`; tests `9b5b014b183008346eb2229d79629286584a7850ae5a056a5524359d3dda1828`.

Next: verify exact atomic update/diff and required checks; finish existing PR through normal merge; verify deployed services. Use supported corrected-edition workflow, or document why ordinary flow requires a separate fresh assessment. Only the authenticated owner may review/approve that exact edition. Inspect actual receipts/final pages/companions/manifest and prove identical supported repeat retrieval before A0–A8 shipment. Preserve original approved bytes; no inherited approval, password requests, repeat evidence upload or client transmission.
