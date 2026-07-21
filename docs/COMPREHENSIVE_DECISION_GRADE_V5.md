# Comprehensive Decision-Grade Report v5

This release upgrades the native Comprehensive report from a stage-oriented evidence dump into a decision-grade client package while preserving the immutable-evidence and human-review boundaries.

## Canonical presentation

- Technical score and technical band are score-derived.
- Evidence assurance is independent from the score.
- Client-delivery authorization is independent from both.
- Human review remains mandatory.

## Truth corrections

- Dependency, static-analysis, and secret findings are counted by their scanner category.
- Unavailable secret-history tools do not create secret findings.
- Named complexity hotspots and measured complexity statistics are surfaced in the architecture section.
- Core-stage page counts are distinguished from final package page counts.
- Limitation accounting distinguishes stages, distinct records, score-affecting records, and informational disclosures.

## Client package

The generated package includes an executive decision brief, score and assurance dashboard, executive risk register, detailed findings register, architecture/data-flow view, executable six-month roadmap, staffing sequence, evidence appendix, findings CSV, evidence CSV, canonical JSON, HTML, and PDF.

## Production boundary

The decision-grade binding is installed before native providers and before production executors are built. Missing evidence remains visible and fail-closed. No report may be delivered until an authorized human approves the exact immutable package.
