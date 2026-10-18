# Retained PDF cache policy scope

Reuse is process-local and binds exact stored input, history commitment, and the
observed live implementation policy. Warm-ticket invalidation cannot mint a new
entry under the old ticket, including the tested warm-ticket A→B→A case.

These snapshots do not detect a transient A→B→A replacement wholly inside a cold
render. This is not a universal hot-swap or ABA guarantee. The supported scope is
a fixed process policy, with observed binding changes invalidating reuse.
Installed first-render rebinding can prevent initial admission; a subsequent
stable render may qualify. No first-timeout or cross-process capacity guarantee
is established.

The PDF download UI recognizes the process-wide busy response only for HTTP 503,
JSON `detail.reason === "retained_pdf_preparing"`, and an integer `Retry-After`
from 1 through 60 seconds (currently 5). The message refers to a PDF, not this run:
the token can belong to another report. Retry remains a manual user action.
Other PDF download errors retain their existing handling.
