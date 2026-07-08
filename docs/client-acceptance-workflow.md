# Human approval and client acceptance workflow

This update adds a formal acceptance gate after NICO prepares an Express assessment and evidence bundle.

## Purpose

NICO can collect evidence, score sections, generate reports, and build a defensible evidence bundle. That does not mean a report is client-accepted. Client delivery must stay gated by human review and explicit signoff.

## Acceptance gate

Each hosted Express assessment now receives a `client_acceptance` object with:

- acceptance status
- client delivery allowed flag
- required signoffs
- evidence checklist
- blockers
- unavailable-data disclosures
- findings disclosures
- evidence bundle hash

NICO sets `client_delivery_allowed=false` until a client acceptance approval is approved.

## Status values

Possible gate statuses include:

- `blocked_missing_evidence`
- `ready_for_human_signoff`
- `ready_for_human_signoff_with_disclosures`
- `accepted` after approval status is approved
- `needs_more_evidence`
- `rejected`

## API endpoints

- `GET /client-acceptance/{run_id}` checks the latest acceptance state.
- `POST /client-acceptance/request` creates a signoff request.
- `POST /client-acceptance/{approval_id}/{status}` transitions the signoff.

The transition endpoint accepts approval states supported by the approval queue. It also accepts `accepted` as an alias for `approved`.

## Required signoffs

The default gate requires:

- technical reviewer signoff
- client or authorized representative signoff

## Safety boundary

The acceptance workflow does not automate final client claims. It records whether delivery is allowed after human approval. If evidence is missing, unavailable, or disputed, the correct state is `needs_more_evidence` or `rejected`, not accepted.
