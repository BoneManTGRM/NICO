# Operator diagnostic boundary

Public assessment users receive bounded service-readiness language only. Database adapters, volume paths, deployment variables, backend origins, and raw internal error codes are not rendered in the client workspace.

Authorized operators retain diagnostics through:

- `/diagnostics/comprehensive-runtime`
- production acceptance logs
- request correlation IDs returned by the proxy
- deployment service logs
- the Operations workspace where authorization permits

This separation prevents infrastructure details from leaking to clients while preserving enough evidence to repair production safely.
