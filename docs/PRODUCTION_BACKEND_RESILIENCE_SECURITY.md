# Security boundaries

- Backend candidates come only from deployment environment variables.
- Embedded URL credentials are rejected.
- Production candidates must use HTTPS.
- The existing route and method allowlist remains authoritative.
- Retry metadata does not expose backend hosts.
- Retries do not alter assessment authorization, evidence, scoring, or delivery approval.
