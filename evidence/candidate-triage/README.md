# Candidate technical triage evidence

This directory retains proposal-only technical triage evidence for scanner candidates that were reconciled against the exact assessed commit `9c876ba4e3e9bb152de52567232038e52a6bbb3e`.

The compact artifact is split into ordered `technical-triage-9c876ba4.part-*.b64` files so repository writes cannot silently truncate the gzip/base64 payload. The runtime concatenates the contiguous parts, validates base64 and gzip integrity, then validates the retained schema and counts before using any technical verdict. The artifact represents 662 one-result-per-candidate technical triage records: 624 `not_actionable`, 38 `needs_review`, and 0 `confirmed`. Its proposed system dispositions are 607 `approved_or_nonblocking`, 17 `excluded_test_only`, and 38 `review_required`.

These records are not human approval, risk acceptance, or client-delivery authorization. Runtime import is allowed only for exact or semantic cross-SHA lineage. Evidence-changed and newly observed candidates must be reviewed again. Canonical candidate dispositions and score-driving totals are not changed by the technical-triage import.
