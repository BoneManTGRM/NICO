# Qualified lexical binding in reviewer assistance

The optional `nico.reviewer-lexical-binding.v1` packet extension carries existing
B603/B607 analysis to the reviewer. It does not create a verdict or disposition.
Only `candidate_call_fact(candidate, trusted_capture, full_scope)` issues facts;
scanner fields and raw embedded parser claims cannot issue this extension.

The exact field allowlist contains the extension/resolver versions, qualified API,
import/call lines, SHA-256, Git blob identity, normalized path, five-field scope and
canonical candidate fingerprint. No argument values or arbitrary narrative are
retained in the lexical proof. Existing persisted `argument_observations` remain
as a sanitized object of `argument_form`, `executable_path`, and `shell_keyword`
enums only (at most three short strings). Invalid or absent values are omitted;
embedded `api_binding` and arbitrary extras are discarded. `unspecified` shell
means no explicit keyword observation, including `**kwargs`; it never means
`false`. Explicit `false` is syntax only and does not resolve dynamic kwargs or
runtime behavior. The existing GET/UI contract does not expose these argument
enums, including from legacy packets. This feature is lexical-binding assistance,
not newly displayed argument analysis. GET projection validates the saved extension against the candidate,
source reference, scope, versions and field allowlist without parsing or fetching.
This is a trusted-persistence contract, not cryptographic issuer authentication.
Legacy packets remain readable but cannot claim qualified lexical binding.

Each extension is limited to 2,048 serialized ASCII JSON bytes. Extensions are
included in canonical record order up to 256 KiB per investigation/projection;
over-budget extensions are omitted, never downgraded to a positive safety claim.
Existing candidate population and analysis budgets remain unchanged.

The reviewer queue is separately enriched and sorted. Its indices/fingerprints
are not canonical-register indices/fingerprints. The UI requires a unique ID in
both arrays, otherwise suppressing source assistance. Backend register and row
fingerprint validation still applies before projection. Legacy projections may
show generic assistance for unique IDs, never qualified binding.

English and es-MX explicitly distinguish static lexical binding from runtime
safety. Runtime dispatch/import hooks, production reachability, untrusted input,
environment, working directory, executable lookup and mitigations remain open.
No shell or argument safety claim is made, including for absent shell keywords,
`**kwargs`, or dynamic arguments. Conflicting scanner claims remain review work.
All dispositions, QC, grouping, scores, approvals and delivery gates are unchanged.

Validation uses synthetic exact-byte captures. These checks establish fixture
coverage, not production effectiveness, candidate clearance or time saved.
