# Production Backend Resilience Release Checklist

1. Confirm `NICO_API_URL` or `NICO_BACKEND_URL` is set to the public HTTPS backend origin in the frontend deployment.
2. Confirm the backend runs `nico.api.comprehensive_production_bootstrap:app`.
3. Verify `GET /diagnostics/comprehensive-runtime` through `/api/nico` returns JSON.
4. Start one authorized Comprehensive assessment from the public domain.
5. Confirm a transient backend restart does not create a second run and the original run ID is recovered.
6. Confirm permanent backend failure returns structured `assessment_backend_unreachable` metadata.
7. Confirm unauthorized and non-allowlisted proxy routes remain blocked.
