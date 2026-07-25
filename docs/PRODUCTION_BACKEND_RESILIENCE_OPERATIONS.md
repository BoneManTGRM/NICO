# Operational response

When the public workspace reports a retryable backend failure:

1. Verify the backend deployment is running and publicly reachable over HTTPS.
2. Verify the frontend deployment variable resolves to that origin.
3. Use the displayed run ID to recover persisted state rather than starting duplicate runs.
4. Re-run only after service health is restored.
5. Do not interpret awaiting scores as a failed technical assessment.
