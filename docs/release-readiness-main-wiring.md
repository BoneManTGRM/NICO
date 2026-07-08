# Release readiness main API wiring

This update mounts the release readiness route in the main hosted API.

Mounted endpoint:

`POST /release/readiness`

`GET /targets` now lists the route in `workflow_endpoints`.

The route returns a readiness artifact from supplied evidence.
