# Ordinary review volumes: isolated core checkpoint

This is an uninstalled core, not a released report format or a repair of the
production over-60-page failure. No existing renderer, endpoint, approval path,
UI, or v1 artifact schema imports it. Do not attach its output to a v1 package:
legacy approval hashes do not cover unknown extra-volume fields.

## Contract and scope

`ordinary_review_bundle_v2.build_review_bundle(identity, sections)` accepts
ordered `(section_id, validated_client_pdf_bytes)` pairs. Identity contains exact
run, repository, commit SHA, canonical truth digest and `en`/`es-MX` locale.
The caller must establish those facts and validate the client-facing source
content. The core does not establish assessment truth, completeness of findings,
source authorization, or finality by inspecting arbitrary supplied PDFs.

Each source page is copied without scaling/re-rendering. Ordered section/page
coverage includes content-stream, extracted-text and geometry fingerprints.
The output keeps an entire section together when it fits a fresh volume; a
larger section continues at existing page boundaries. No pages are dropped to
fit. Numbered volume index pages count toward the 60-page finished-volume bound.
PDF bookmarks and decimal page labels identify local page destinations. Existing
source-page printed counters are preserved; the eventual assembler must provide
pre-pagination sections so stale global counters cannot reach a released bundle.

The manifest binds ordered members to exact final PDF hashes, sizes, actual page
counts, source sections, coverage and identity. Every volume remains a blocked
automated draft. Retrieval validation requires the expected manifest digest from
an independently retained review identity, not from a download request. Member
order, safe generated filenames, exact PDF file population, coverage and generated
navigation are validated. The deterministic ZIP contains these PDF members and
the bundle manifest only; it is not yet the existing eight-artifact evidence ZIP.

The builder returns a complete in-memory file set only after all volumes validate.
It performs no writes. Atomic persistence, the structured exports, artifact-family
manifest, and whole-bundle approval binding remain integration work.

## Measured bounds

Core tests: 31 passed in 3.23 seconds; peak RSS 108,332 KiB including pytest imports.
The existing dense worksheet fixture rendered 36 pages in each locale. Repeating
that fixture as 13 separately identified sections exercised 468 source pages:

| Locale | Final volumes/pages | Final PDF bytes | Build/validate seconds | Peak process RSS KiB |
| --- | --- | --- | --- | --- |
| en | 13 / 481 | 1,097,103 | 3.631 | 108,972 |
| es-MX | 13 / 481 | 1,115,508 | 3.669 | 113,324 |

Provisional core bounds are 480 source pages, 512 final pages, 16 volumes, 128
sections, 4 MiB each for aggregate input PDFs and aggregate output PDFs, and a
60-second cooperative deadline. These bound the tested PDF-copying scope with
headroom over the measured fixtures; they are not production capacity guarantees.
The deadline cannot interrupt a single pypdf/ReportLab operation. A hard worker
time/memory limit and end-to-end measurements are prerequisites for endpoint
activation. These measurements do not cover assessment, upstream rendering,
large images, adversarial PDFs, network delivery or arbitrary repository scale.

Tests also exercise a controlled EN/es input population with different pagination;
the dense worksheet fixture itself has equal page counts in both languages.

## Remaining coupled integration surfaces

1. Composition and final validation: collect all required primary/components and
   prove their complete coverage before partitioning. Existing 60-page v1 checks
   remain unchanged; no unlimited intermediate PDF should escape as a report.
2. Navigation and manifest: current final-worker navigation and manifest rebinding
   mutate one PDF. Create the v2 section/finalization boundary, then freeze all
   files only after every navigation and manifest-related mutation is finished.
3. Structured artifact family: include the existing non-PDF exports, detached
   identity and manifest in a versioned exact member set. Reject extra, missing,
   duplicate and undeclared ZIP members rather than relying on individual hashes.
4. Locale/frozen transport and cache: carry the complete v2 schema through the
   fixed-field projection paths, validate all members, and prohibit Volume-1-only
   downgrade. Preserve immutable historical v1 byte retrieval.
5. UI: label main report as Volume 1 and expose a complete localized bundle with
   clear review/delivery state; test actual mobile and desktop download actions.
6. Approval safety before any v2 exposure: explicitly reject v2 at specialist,
   alternate operator, accepted-edition and delivery authorization entry points.
   A valid first-volume digest must never permit legacy approval or delivery.
7. Shipping completion: version review identities, accepted editions, approval
   receipts, delivery receipts and approved ZIP policy to cover the whole file
   family. Test stale receipts and any member/locale/content mutation.

Whole-bundle customer delivery materially enlarges the scope beyond this core.
The smallest safe path is staged integration of those existing contracts, with
v1 unchanged, followed by whole-bundle approval—not a broad renderer redesign.
Do not present a review-only bundle as customer-delivery completion. Parent owns
the integration decision and publication. The separate KeepTogether optimization
remains unimplemented and unproven against the unavailable production payload.
