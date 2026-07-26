# NICO Architecture and Product Decisions

## ADR-001 — One customer-facing assessment product

**Status:** Accepted

**Decision:** NICO exposes one flagship product: **NICO Comprehensive Technical Assessment**.

Internal compatibility aliases may remain during migration, but they must not create separate customer-visible quality tiers, scorecards, evidence ledgers, or report identities.

**Reasoning:** A single product concentrates engineering and quality effort, avoids intentionally incomplete reports, simplifies sales and operations, and makes every reliability improvement apply to every client.

**Consequences:**

- Scope and price vary by system complexity, evidence volume, repository count, infrastructure breadth, interviews, and required review.
- Quality standards do not vary by package.
- Public product terminology must be machine-tested.
- Stored legacy values require explicit migration or compatibility mapping.

## ADR-002 — Complexity is internal scope metadata

**Status:** Accepted

**Decision:** `small`, `standard`, `complex`, and `enterprise` classify internal workload and risk. They do not alter the required report-quality standard.

**Reasoning:** Engagements require different labor without justifying lower-quality conclusions.

## ADR-003 — One canonical assessment model drives every artifact

**Status:** Accepted

**Decision:** Executive brief, technical report, roadmap, backlog, machine-readable output, PDF, HTML, Markdown, and executive presentation must derive from one canonical assessment model.

**Reasoning:** Independent rendering from separate reasoning paths creates score, severity, count, finality, and roadmap contradictions.

**Consequences:** Cross-format invariant failure blocks delivery.

## ADR-004 — Human review remains a production control

**Status:** Accepted

**Decision:** NICO automates repeatable work but does not independently accept risk, make legal or compliance attestations, approve high-risk architecture, merge protected remediation, deploy production changes, or authorize client delivery.

**Reasoning:** Security judgment and organizational risk authority remain human responsibilities.

## ADR-005 — Missing evidence is not clean evidence

**Status:** Accepted

**Decision:** Required evidence that is missing, failed, timed out, malformed, unsupported, or tied to the wrong immutable baseline must remain explicit and block dependent completion claims.

## ADR-006 — Maturity requires repeated benchmark proof

**Status:** Accepted

**Decision:** A target is achieved only after an automatically measured benchmark meets it on three consecutive complete runs from a clean environment with retained evidence and no unresolved Critical or High regression.

**Reasoning:** Feature existence and one successful demonstration do not establish mature automation.

## ADR-007 — Risk-based remediation authority

**Status:** Accepted

**Decision:** NICO may prepare and test eligible low-to-moderate-risk repairs. Authentication, authorization, cryptography, secrets, tenant isolation, destructive migrations, production infrastructure, billing, compliance controls, production client systems, and material data deletion require explicit human approval before merge or deployment.

## ADR-008 — GitHub-first commercial repository scope

**Status:** Accepted for the current release

**Decision:** Hosted commercial repository integration remains GitHub-native until the flagship Comprehensive workflow, external pilot, recovery proof, security hardening, and maturity benchmarks are complete.

**Reasoning:** Provider expansion must not dilute the production-quality work needed for the current product.
