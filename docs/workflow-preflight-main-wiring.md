# Workflow preflight main API wiring

This update mounts the workflow preflight API route registrar in the hosted FastAPI app.

## Mounted endpoints

The hosted app now exposes:

- `POST /workflow/preflight`
- `POST /workflow/preflight/batch`

## What changed

`nico/api/main.py` now imports:

`register_workflow_preflight_routes`

and calls:

`register_workflow_preflight_routes(app)`

near the existing service catalog route registration.

## Target discovery

`GET /targets` now lists both workflow preflight endpoints in `workflow_endpoints`.

## Boundary

These endpoints prepare preflight packages only. They do not execute Express, Mid, or Retainer workflows.
