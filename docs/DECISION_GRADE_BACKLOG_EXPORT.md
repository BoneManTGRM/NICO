# NICO Decision-Grade Backlog Export v1

## Purpose

The backlog exporter converts the retained decision-grade contract into implementation-ready remediation work without rewriting findings by hand.

It consumes:

- every P0 and P1 finding;
- P2 findings that are already mapped to a roadmap work package;
- the associated roadmap package, owner, effort, dependencies, implementation sequence, acceptance criteria, and residual risk;
- the immutable assessment identity and assessed commit SHA.

## Deduplication rule

Findings mapped to the same primary roadmap work package are combined into one backlog item. The item preserves every related finding ID, evidence location, business impact, and acceptance criterion. This prevents duplicate tickets when one remediation package resolves several related findings.

## Generated formats

Each Comprehensive package receives:

- Markdown remediation backlog;
- structured JSON;
- GitHub issue-ready objects;
- Jira-compatible CSV;
- Linear-compatible CSV.

Every format has a SHA-256 digest. The complete export manifest is attached to the top-level assessment result and report package.

## Required fields

Every item includes:

- stable backlog/work-package ID;
- title and priority;
- related finding IDs;
- problem statement;
- evidence references;
- business impact;
- scope;
- ordered implementation guidance;
- owner role and effort;
- dependencies;
- binary acceptance criteria;
- residual risk;
- source assessment ID;
- immutable assessed commit SHA;
- labels and time window.

## Safety boundary

The exporter never creates external issues automatically. `automatic_external_creation_allowed` remains `false` at the manifest, format, and item levels. Human review and explicit authorization are required before any GitHub, Jira, or Linear import or issue creation.

If the contract is absent, malformed, not commit-bound, or produces an incomplete export, the Comprehensive result fails closed with `decision_grade_backlog_export_failed`.
