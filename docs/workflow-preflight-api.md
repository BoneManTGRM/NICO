# Workflow preflight API routes

This update adds route handlers for workflow preflight checks.

## Endpoints

The route registrar exposes:

- `POST /workflow/preflight`
- `POST /workflow/preflight/batch`

## Purpose

These routes let the frontend or hosted API prepare a workflow request before running Express, Mid, or Retainer.

## Router module

The new module is:

`nico/workflow_preflight_api.py`

It includes:

- `WorkflowPreflightRequest`
- `WorkflowPreflightBatchRequest`
- `workflow_preflight_response`
- `workflow_preflight_batch_response`
- `register_workflow_preflight_routes`

## Boundary

The routes only return preflight packages. They do not execute the underlying workflow.

## Follow-up integration

A later wiring update should mount `register_workflow_preflight_routes(app)` in the main API app.
