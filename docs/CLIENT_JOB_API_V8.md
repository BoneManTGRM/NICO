# Client Job Mode API v8

This adds first-class NICO APIs for building and exporting client audit packages.

## Endpoints

- `POST /client-job/package`
- `POST /client-job/export`
- `GET /client-job/{job_id}`
- `GET /client-job/{job_id}/exports`

These are internal NICO backend APIs. They do not add third-party data-provider subscriptions.

## Package request fields

- `customer_id`
- `project_id`
- `client_name`
- `project_name`
- `repository`
- `source_scope`
- `authorization_statement`
- `quote_text`
- `product_evidence_text`
- `assessment`

## Export formats

- `json`
- `markdown`
- `html`
- `pdf`

PDF exports are returned as base64 content with `mime_type=application/pdf`. Text formats return `content`.

## Delivery rule

Every package remains human-review gated. NICO can prepare a draft package, but client-final delivery requires a qualified human review of evidence, missing data, findings, and wording.

## Storage

The memory fallback now includes:

- `client_jobs`
- `client_job_exports`

The Postgres schema includes matching future tables. Automatic migration remains disabled in the hosted safe build.
