# Service catalog main API wiring

This update mounts the service catalog API route registrar in the hosted FastAPI app.

## What changed

The main API app now imports:

`register_service_catalog_routes`

and calls:

`register_service_catalog_routes(app)`

after CORS middleware setup.

## Mounted endpoints

The hosted app now exposes:

- `GET /service-catalog`
- `GET /service-catalog/{workflow}`
- `POST /service-catalog/intake-readiness`

## Targets endpoint

`GET /targets` now includes the service catalog endpoints in its `workflow_endpoints` list so clients and frontend callers can discover them.

## Safety boundary

The endpoints only expose catalog and intake readiness logic. They do not run scans, bypass authorization, approve client delivery, or make production-impacting changes.
