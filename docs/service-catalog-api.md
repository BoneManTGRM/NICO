# Service catalog API endpoints

This update adds a FastAPI route registrar for the service catalog and intake readiness workflow.

## Endpoints

The route registrar exposes:

- `GET /service-catalog`
- `GET /service-catalog/{workflow}`
- `POST /service-catalog/intake-readiness`

## Purpose

These endpoints let the hosted API or frontend retrieve the NICO service catalog and check which workflow a client should use before submitting a full assessment request.

## Router module

The new module is:

`nico/service_catalog_api.py`

It includes:

- `ServiceIntakeRequest`
- `service_catalog_response`
- `service_catalog_item_response`
- `service_intake_readiness_response`
- `register_service_catalog_routes`

## Safety boundary

The API endpoints do not bypass authorization. They only describe services and score intake readiness. Express audits still require explicit authorization before execution. Client-facing or production-impacting decisions still require human review and approval.

## Follow-up integration

A future wiring update should call `register_service_catalog_routes(app)` from the main API app so these route handlers are mounted in production.
