# Service catalog and intake readiness

This update adds a service catalog and intake readiness module for NICO workflows.

## Purpose

NICO now has enough workflow modules that clients need a clear intake path. The service catalog defines what each workflow is for, what evidence it needs, what it delivers, and which workflow endpoint should be used.

## Artifact schemas

The catalog returns:

`nico.service_catalog.v1`

The intake readiness check returns:

`nico.service_intake_readiness.v1`

## Services

The first catalog version covers:

- Express Technical Health Assessment
- Mid Product and QA Assessment
- Ongoing Product Engineering Retainer

## Intake readiness

The readiness module checks supplied evidence and returns:

- recommended workflow
- target service
- readiness score
- required fields
- present fields
- missing fields
- blockers
- next action
- human-review requirement

## Safety boundary

The catalog does not bypass authorization. Express audits require explicit authorization. All workflows remain evidence-bound, and client-facing or production-impacting decisions require human review and approval.

## Next integration step

A follow-up update should expose the catalog through API endpoints such as:

- `GET /service-catalog`
- `GET /service-catalog/{workflow}`
- `POST /service-catalog/intake-readiness`

This PR keeps the catalog logic isolated first so it can be tested without touching the main API router.
