# Phase 4: Production Client-Delivery Hardening and End-to-End Proof

## Product boundary

NICO has one assessment product and one client report: **NICO Comprehensive**. Phase 4 does not create another assessment controller, service tier, report renderer, report pipeline, or client PDF. It composes the existing Phase 2 human-review and accepted-edition authorities with the Phase 3 client-engagement identity contract.

## Runtime integration

`nico.phase4_client_delivery_runtime_v1` terminally rebinds only two existing authorities:

1. the approved-delivery builder used by the protected Comprehensive review action;
2. the immutable-package validator used by the protected approved-download route.

The existing route set, canonical scoring, report synthesis, artifact renderer, reviewer queue, and human decision action remain authoritative.

## Phase 4 approval receipt

An approved delivery now retains a deterministic Phase 4 receipt binding:

- client and project identity;
- customer, client, project, workspace, organization, and tenant scope where present;
- exact Comprehensive run, repository, assessed commit, and evidence-ledger identity;
- authorized scope and read-only access method;
- reviewer identity and role;
- protected authorization basis;
- decision timestamp, residual-risk decision, notes, and approval-record ID;
- exact reviewed Markdown, HTML, PDF, canonical JSON, and available CSV digests;
- review-ledger, review-source, candidate-register, and candidate-disposition digests;
- assessed-repository commit separately from NICO generator/build truth and mutable operational history;
- explicit one-product, one-report, human-review, and client-final classification.

Automation cannot satisfy the final human reviewer identity contract. Unsupported or unproven deployment-version fields remain `unavailable`; the receipt does not convert absence into deployment proof.

The accepted edition freezes the operational-history reference used by the receipt. Attaching the immutable package may recompute the enclosing run-record integrity hash, but that bookkeeping update does not invalidate the receipt it just enclosed. Material report, evidence, candidate, disposition, client/project, repository, commit, review, and generator-version truth is still recomputed and must match exactly.

## Fail-closed behavior

The controlled-client contract rejects missing authorization or identity, non-read-only access, repository/scope mismatch, unresolved or mismatched commits, required scanner failure, unsupported ecosystems, malformed candidate registers, stale/missing lineage, incomplete triage, unresolved mandatory individual review, cross-client/project/run review state, missing required artifacts, alternate report products, internal/test packages presented as client final, unauthorized reviewer roles, automation approvers, artifact mutation, stale receipts, and delivery-package or evidence-manifest hash mismatch.

Any material report, evidence, candidate, disposition, score-bearing canonical JSON, or identity change changes a bound digest and invalidates the old receipt. The protected download validator re-evaluates the record against the exact immutable receipt rather than trusting a prior boolean. Expected inherited validation failures, including stale or cross-scope review state, are returned as bounded invalid-package evidence rather than escaping as unhandled exceptions.

## Repository-agnostic acceptance fixtures

Deterministic Phase 4 fixtures cover structurally different supported repositories:

- Python service;
- Node/TypeScript application;
- mixed Python and TypeScript repository.

The fixtures use repositories outside `BoneManTGRM/NICO` and contain no NICO-specific paths or historical candidate counts. Unsupported ecosystems are represented as `unsupported_not_assessed` and are blocked rather than populated with fabricated scanner evidence.

Fixtures are engineering evidence only. They do not replace real authorized external-repository pilots.

## Operational workload truth

Phase 4 projects candidate, triage, individual-review, grouped-review, cluster, QC, disposition, finding, external-evidence, runtime, automated-processing, reviewer-action, elapsed-review, and active-review metrics. The approximately four-combined-specialist-hour objective remains a design target. Exceeding it is surfaced and does not hide candidates, lower review requirements, change a technical score, or authorize delivery.

## Controlled paying-client pilot gate

Code and CI can prove deterministic lifecycle, isolation, integrity, and fail-closed behavior. A controlled paying-client pilot still requires all of the following on the exact final merge SHA:

1. required CI, security, authorization, review, report-preservation, and production-acceptance checks pass;
2. deployed backend and frontend identities are established where infrastructure exposes them;
3. a fresh external authorized repository completes the Comprehensive workflow;
4. two authorized cybersecurity specialists exercise the exception-first workflow;
5. the exact immutable package is explicitly approved by an authorized human;
6. protected client delivery succeeds only after that approval;
7. the delivered archive and receipt revalidate after retrieval;
8. actual combined specialist time is measured without invasive monitoring.

Until that outside-repository evidence exists, Phase 4 supports a **controlled pilot candidate**, not broad commercial-readiness or superiority claims.
