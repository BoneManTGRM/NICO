# NICO Service Model

NICO exposes two customer-facing assessment services and one recurring operating service.

## 1. NICO Express Technical Assessment

Express is the fast, evidence-bound technical baseline.

It covers repository quality, dependency and library health, secrets exposure signals, static analysis, CI/CD, architecture and technical debt, complexity, velocity, prioritized findings, and a decision-oriented executive report.

Use Express when a founder, investor, agency, or engineering team needs a rapid technical diagnosis before deciding whether deeper diligence is required.

## 2. NICO Comprehensive Technical Assessment

Comprehensive replaces the overlapping customer-facing Mid and Full products.

It includes everything in Express plus deeper scanner execution and triage, functional QA, platform parity where applicable, deployment and infrastructure review, stakeholder and business-context evidence, developer delivery-process analysis, requirements traceability, a six-month roadmap, staffing and sequencing recommendations, and one final human-reviewed client package.

Comprehensive uses:

1. one simple intake;
2. one immutable repository snapshot;
3. one run ID;
4. one evidence ledger;
5. one canonical score and truth state;
6. one final report package.

Legacy `mid`, `full`, and `deep` identifiers remain supported as internal execution profiles and API aliases during migration. They must resolve to the customer-facing `comprehensive` service and must not appear as three separate assessment products.

## 3. NICO Monitor + Execute

Monitor + Execute is a recurring operational service, not another assessment tier.

It covers ongoing monitoring, approved remediation, sprint and release oversight, release verification, roadmap execution, evidence retention, and human approval records. It remains read-only or recommendation-only unless the customer has explicitly authorized a specific execution action.

## Customer decision

- Choose **Express** for a rapid technical baseline.
- Choose **Comprehensive** for complete technical diligence, QA, operating-model analysis, roadmap, and resourcing.
- Use **Monitor + Execute** after an assessment when recurring oversight or approved execution is required.

## Migration rules

- Preserve existing Mid and Full run IDs, retained evidence, URLs, and API compatibility.
- Do not combine separately generated reports after the fact.
- New customer-facing labels, pages, reports, and sales material must use Express or Comprehensive.
- Internal Mid and Full execution modules may remain until their capabilities are migrated safely behind the Comprehensive orchestrator.
- No migration may weaken authorization, exact-snapshot identity, evidence truth, human review, testing, rollback, or client-delivery controls.
