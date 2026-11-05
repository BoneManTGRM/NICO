# Architecture policy conformance — function maintainability v1

This additive profile evaluates actual target-repository source observations against two fixed normative rules, not NICO's own test passes. It is a narrowly named function-maintainability policy, not a replacement for Architecture and Technical Debt, a calibrated quality/debt-cost score, or delivery velocity. No legacy complexity_score, overall maturity or delivery formula is changed. Existing human/client-delivery gates remain authoritative.

Version: `nico.architecture-policy.function-maintainability.v1`.

## Rules and criticality

- `function_cc_max_20`: every enumerated eligible Python/JS/TS function must have CC<=20. Any CC>=21 fails this rule. This version explicitly designates it critical **for this policy only**, as a conservative engineering convention, not an empirically calibrated security/business severity.
- `function_nesting_max_4`: every such function must have nesting<=4. Any nesting>=5 fails this rule; noncritical in this version.

Each rule counts once across the qualified function population. Different languages keep existing parser conventions; this is a normative conjunction, not averaging cross-language measurements. Existing measurement tables retain per-language distributions, absolute violations and sum(CC-1). Adding1000trivial functions cannot turn either failed rule into a pass or change its share of the rule denominator. Extracting helpers can change per-function bands without reducing total decision burden; no improvement/quality claim follows automatically.

No custom arbitrary caller-supplied pass/fail flags are accepted. `build_policy` calls the existing conformance builder with the trusted persisted collection witness. Exact run/repository/customer/project/snapshot identities, collection commitments, source/input hashes and acquisition coverage must satisfy existing validation. This reuses receipts and persistence; it is not new cryptographic attestation. Missing/contradictory/untrusted source inputs leave both rules unknown.

## Status and denominators

The fixed inventory always has2rules. `pass`, `fail`, `unknown`, `not_applicable` counts sum to2. Unknown remains in the normative denominator; it never becomes pass or silently disappears. Each rule requires its full dimension population; missing nesting can leave nesting unknown while retaining a qualified CC failure.

Only a qualified, completely acquired eligible population with zero enumerated functions makes rules N/A. N/A remains visible with the explicit measured-empty reason. Unsupported sources remain excluded, not passed; this is not whole-repository architecture N/A. There is no arbitrary user N/A flag or scope omission mechanism.

Denominator=2−justifiedN/A. Percentage=100×passed/denominator only when unknown=0 and denominator>0. Otherwise percentage is absent and display says no qualified percentage. It is percentage of these rules, not percentage of architecture quality. Critical failure count/status is independent: a CC failure remains blocked even when a percentage is50 or another rule unknown. Unknown critical evidence displays unknown, not clear. Policy blocking does not introduce a new acceptance/approval gate.

Coverage includes resolved rule count, fixed/applicable denominator, existing acquisition coverage/exclusions, exact identity/inventory/producer hashes. Public tables show counts, rules, unknown/N/A reasons, criticality and scope. Existing source measurement/acquisition tables remain alongside this profile.

## Integration and presentation

`architecture_data_flow_provider` attaches a separately named structured evidence object and two tables. Existing report stage summarization retains the object without flattening it into prose; English/es-MX renderers translate authored display copy while preserving machine evidence and policy version. Canonical sanitization/localization preserve the raw policy object. No new transport, storage, dependency or remote service.

The broad architecture and velocity cards can remain unscored. This profile is useful evidence with an honest narrow scope, not a hidden numeric adapter. Topology/boundary obligations, runtime behavior, semantic duplication and verified economic debt are explicitly outside this policy and remain unassessed. This limitation is visible in both languages.

## Validation and limits

Synthetic collector->trusted generated-row persistence->provider->stage->Markdown/HTML/PDF tests cover completepass,CCcriticalfailure,nesting4/5,emptyN/A,missing/partial/wrongidentity/contradictory/fakewitness,partialnestingwithknownCCfailure,1000-function dilution,and final artifact/approval preservation. Neighboring witness/conformance/score-truth tests are run in isolated processes with existing dependencies. Runtime input source is synthetic; no actual target assessment or production scoring is executed.

Independent review must assess the normative critical designation and whether this narrowly scoped profile is useful under its explicit title. It does not constitute agreement to redefine the existing broad cards. Local implementation only; publication requires the separately authorized independent review first; no merge/deployment.

## Partial observations and threshold consistency

Every rule retains measured and total function counts. `observed_violations` records qualified observations even when a dimension is partial; `violations` is the exhaustive count only for a complete applicable dimension. Partial rules remain unknown, suppress the policy percentage and explicitly label observed counts non-exhaustive in English/es-MX. Known negative observations are never hidden or converted into pass. A source metric threshold must be an integer matching the versioned policy threshold before its counts can be used; mismatch leaves the rule unknown, records both thresholds and suppresses the percentage rather than relabeling source counts.

## Compact presentation

The four rule-state counts share an explicitly ordered summary row; resolved/inventory counts share a second row. These are display-only groupings; structured counts, denominators and critical state are unchanged. Policy tables precede the existing measurement tables. PDF source-table narrative limitation rows span both columns with their complete translated label and text; vertical padding is 2pt while the existing 7.1pt minimum font and 9pt leading remain unchanged. No evidence rows are omitted and the existing 34-page synthetic final-report budget remains enforced.
