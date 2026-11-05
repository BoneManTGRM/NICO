# Smallest complete ordinary report-bundle delivery path

Baseline: main 4886d4bf. Production acceptance still fails at
`pdf_total_pages_limit`; sparse layout savings are not sufficient. The preserved
multi-volume core is a starting point, not an end-to-end shipping fix.

## Bounded sequence and dependencies

1. **Composition and frozen transport (this slice).** Share the existing primary
   page-selection rules with an explicit bundle composer. Feed all retained primary
   pages and every required component to the existing volume core. Do not change
   the v1 composer or its page gate. Build an exact, deterministic file family
   containing numbered PDFs, all seven non-PDF exports, and detached bundle/family
   manifests and identity. Validate ZIP membership, bytes, order, identity, coverage
   and bounds before returning anything. Add explicit v2 rejection to legacy
   approval/delivery and single-PDF projection boundaries. No endpoint activation
   or automatic production fallback in this slice.
2. **Installed ordinary assembler and retrieval.** Branch at
   `client_report_completion_v2.finalize_client_report_package` using a v2-aware
   final-surface validator that checks content collectively across every volume.
   Reuse the existing canonical projection, source provenance, source population,
   approval status and structured-export builders. Finish navigation before freeze.
   Route v2 around the single-PDF mutation/rebinding chain in
   `comprehensive_artifact_manifest_approval_v1`,
   `comprehensive_manifest_navigation_v1` and
   `comprehensive_final_worker_pdf_reflow_v1`; never send Volume 1 through that chain
   as a complete report. Persist the entire family atomically with a trusted
   manifest digest. Update same-run locale/cache and frozen retrieval in
   `comprehensive_same_run_locale_report_v1`, `comprehensive_localized_export_v1`
   and `comprehensive_mobile_recovery_v1`. Update existing download UI to identify
   Volume 1 and offer the complete bundle. Require worker-level time/memory limits.
3. **Whole-bundle approval and delivery (required for shipping).** Version review
   artifact identities, accepted editions, reviewer/operator approval records and
   delivery receipts around the family manifest digest. Retain the existing
   authenticated action/ownership/review-ledger checks. Update
   `decision_grade_accepted_edition_guard_v1`, `decision_grade_accepted_edition_v2`,
   `comprehensive_review_decision_v1`, `comprehensive_client_delivery_contract_v1`,
   `comprehensive_run_service`, `comprehensive_operator_approval_v1`,
   `comprehensive_operator_delivery_v1`, `comprehensive_delivery_authorization_v1`
   and approved-delivery package validators. Keep approval separate from delivery
   permission. No member rewrite may occur after its approval-bound hash is frozen.
   Certificates must be detached and bind the exact family; a new approved edition
   must explicitly map any changed presentation bytes back to the reviewed family.
4. **Installed acceptance and controlled production acceptance (parent-owned).**
   Exercise complete EN/es generation, freeze, download, approval, authorization,
   retrieval and stale/tampered receipt rejection using representative dense inputs.
   Only after exact-head CI and independent review should parent deploy and run a
   controlled retained-report acceptance. No assessment rerun is needed by design.

## Explicit shipping completion checklist

- [ ] Complete primary, worksheet, register, exact-source and required appendix
      content reconciles against the authoritative projected population exactly
      once, including sections split across physical volumes.
- [ ] Every final volume has 1–60 pages with index space accounted for, readable
      typography, correct local navigation and unambiguous volume identity.
- [ ] The exact file set includes all existing structured exports; no omitted,
      extra, swapped, reordered or duplicate members are accepted.
- [ ] Run/repository/source SHA/canonical truth/locale and final member bytes are
      bound to a trusted immutable family digest.
- [ ] Partial generation/freeze failures expose no ready package or partial cache.
- [ ] Frozen v1 retrieval remains byte-identical; v2 never downgrades to Volume 1.
- [ ] Regenerated localized families require their own approval; no mixed locales.
- [ ] Reviewer and operator approval cover every member; old receipts cannot
      approve new volumes or a changed family. Delivery permission remains separate.
- [ ] Complete authorized ZIP delivery and mobile/desktop download actions work.
- [ ] Page/byte/volume limits and hard worker memory/time bounds fail explicitly
      without cutting evidence; resource measurements cover the full installed path.
- [ ] Exact-head required CI, independent review and parent-controlled acceptance
      confirm the actual retained report delivers successfully and usefully.

## Scope and timeline risk

This is coupled work across a single-PDF pipeline, not a gate constant change.
The existing wrapper chain repeatedly changes the PDF and rebinds its manifest;
blindly teaching each wrapper about a list of PDFs risks omissions and stale hashes.
The smallest approach is one explicit v2 assembly/freeze branch sharing existing
truth validators and exporters, with v1 untouched, then a versioned whole-family
approval path. That is a material integration task, but does not require a new
assessment engine, permission model, queue, or general renderer rewrite.

This slice alone is deliberately not shipping completion. No reliable calendar
estimate follows from the core benchmark. If the installed branching point cannot
be isolated without widespread wrapper changes, stop after this tested slice and
report that boundary before extending scope.
