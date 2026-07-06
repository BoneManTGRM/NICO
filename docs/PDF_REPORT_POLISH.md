# Polished Express PDF report output

NICO Express assessment PDFs are generated from structured assessment data, not from a raw Markdown dump.

## PDF goals

- Client-ready first page with title, repository, client, project, generated timestamp, assessment quality, maturity, and human-review warning.
- Scorecard table for section status and scores.
- Separate section blocks for evidence, findings, and unavailable data.
- Footer on every page with page number and human-review reminder.
- Controlled truncation for long evidence lists so the PDF stays readable.
- Markdown and HTML remain available for full detail.

## Safety and accuracy

- Missing evidence remains visible.
- Unavailable data is not hidden.
- The PDF does not claim verification that the assessment data does not support.
- Human review remains mandatory before client-facing delivery.

## Implementation

The PDF is generated in `nico.assessment_quality.polish_express_result` after evidence-quality guardrails have been applied. The frontend continues to use `reports.pdf_base64` for the Download PDF button.
