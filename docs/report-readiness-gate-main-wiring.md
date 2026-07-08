# Report readiness gate main API wiring

This update mounts the report readiness gate route in the main hosted API.

Mounted endpoint:

`POST /reports/readiness-gate`

`GET /targets` now lists the route in `workflow_endpoints`.

The route returns a readiness gate artifact from supplied evidence before a fresh Express report is trusted.
