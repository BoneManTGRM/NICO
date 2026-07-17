# Provider collection runtime

NICO treats provider collection state as evidence, not as an implementation detail.

A collection is ready only when it is read-only, bound to one repository, bound to one immutable revision, complete for all requested capabilities, and fully paginated. Authentication failures, provider outages, rate limits, incomplete pagination, and missing capabilities remain explicit limitations and cannot be scored as successful evidence.

Supported collection modes are API, scheduled polling, webhook events, generic Git transport, and uploaded archives. Generic Git and archives intentionally expose narrower capabilities than full provider APIs.

This runtime layer does not store credentials or perform network requests. Provider clients must translate their native responses into these states and preserve the exact repository and revision identity before evidence enters assessment scoring or reports.
