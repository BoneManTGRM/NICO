# Hosted smoke test main API wiring

This update mounts the hosted smoke-test route in the main hosted API.

Mounted endpoint:

`POST /hosted/smoke-test`

`GET /targets` now lists the route in `workflow_endpoints`.

The route returns a structured smoke-test artifact from supplied evidence.
