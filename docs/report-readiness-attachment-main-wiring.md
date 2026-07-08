# Report readiness attachment main API wiring

This update mounts the report readiness attachment route in the main hosted API.

Mounted endpoint:

`POST /reports/attach-readiness`

`GET /targets` now lists the route in `workflow_endpoints`.

The route combines a supplied report payload with a supplied readiness gate artifact before delivery.
