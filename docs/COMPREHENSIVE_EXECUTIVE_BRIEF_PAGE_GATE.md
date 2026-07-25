# Comprehensive Executive Decision Brief Page Gate v1

## Purpose

The Comprehensive report has a dedicated Executive Decision Brief on PDF page 2. This gate converts that layout convention into a deterministic delivery requirement.

A report is blocked when the final PDF does not prove that the brief occupies exactly one page and remains separated from the technical scorecard.

## Final-artifact checks

Validation runs after the premium front-matter pages have replaced the original PDF pages. It therefore evaluates the exact final artifact rather than an intermediate renderer output.

The gate requires:

- a valid PDF with at least three pages;
- exactly one page containing the `Executive Decision Brief` heading;
- that heading to appear on page 2 only;
- the technical scorecard to begin on page 3 or later;
- the page-2 decision dashboard;
- top business consequences;
- package identity;
- a visible `What this means for you` statement;
- an immutable-commit, speed, repeatability, and comparison-value statement;
- a bounded page-2 text-density range.

The report package retains the page numbers, marker results, and validation outcome as machine-readable evidence.

## Cross-format language

Markdown and HTML receive the same required decision language:

- what the client should do next;
- why release or client delivery remains conditional;
- that the assessment is bound to an immutable commit;
- that repeat runs compare versioned structured evidence instead of rewritten narrative.

## Failure behavior

Any PDF parsing, page-boundary, content, or scorecard-separation failure changes the report result to `blocked` with `executive_decision_brief_page_gate_failed`.

The gate does not authorize client delivery. Human review and exact-package approval remain mandatory after the page gate passes.
