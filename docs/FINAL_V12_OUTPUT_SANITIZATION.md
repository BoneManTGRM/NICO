# Final v12 client-output sanitization

The final Express response boundary now sanitizes unavailable complexity measurements before Markdown, HTML, and PDF regeneration. Values such as `max_function_cyclomatic=None` and `density=None` are rendered as `unavailable` rather than exposing Python null-display text to clients.

Generic CI Quick Wins are also suppressed when the current CI/CD section is green and required checks explicitly report success. Historical workflow reliability findings remain visible as separate review items and are not erased.

These changes do not alter scores, evidence provenance, assessed repository contents, or the report-only no-write boundary.
