# Composition/transport slice: explicit and not yet installed

This branch starts from 4886d4bf and incorporates the preserved volume core.
It does not activate a v2 endpoint, change production report selection, authorize
a bundle, or fix the retained production export by itself. The complete shipping
sequence and completion checklist are in `report-bundle-shipping-plan.md`.

## Changes

- `client_pdf_compose_v2` extracts its existing primary-page selection into one
  shared helper without changing the selection rules. V1 still has all its
  existing total-page checks. The explicit `compose_review_bundle` requires the
  review, CI, register and acceptance components, preserves optional human evidence,
  and sends retained pages to the bounded core without truncation.
- `ordinary_report_files_v2` creates a frozen, deterministic file family: all
  numbered PDF volumes; findings/evidence CSV; candidate/backlog JSON; Markdown;
  HTML; canonical JSON; the volume manifest; artifact identity; and a detached
  family manifest. No supporting export is silently omitted. The existing
  `canonical_sha256` implementation binds canonical truth and source identity.
- Transport requires the independently retained family digest and exact run,
  repository, source SHA and locale. Validation checks the ordered full member set,
  final bytes/hashes/sizes, actual PDF counts, volume coverage, canonical identity
  and pending-review authority. ZIP loading rejects undeclared, missing, duplicate,
  unsafe, reordered and substituted entries before returning a family.
- `ordinary_bundle_boundary_v2` identifies v2 only in report-owned containers,
  including serialized canonical JSON and final-report stages. Evidence quotations
  are not format declarations. Legacy review/operator approval, accepted-edition,
  delivery authorization, approved ZIP builders/validators, exact artifact checks,
  locale projection and retained/mobile single-PDF downloads explicitly reject v2.
  A valid Volume 1 hash or previously valid v1 operator receipt confers no bundle
  authority. These small guards are needed across the existing alternate paths;
  they do not alter the authentication or permission model.

The output is complete in memory or construction raises. No persistence, cache
admission, endpoint registration, delivery, or approval is performed by the new
builder. Callers must still prove final-surface semantic completeness and persist
the trusted family digest atomically before exposing the result. Source selection
is the existing v1 projection, not a claim to render all raw/internal scanner data.
Semantic titles and sub-section navigation within component PDFs, source counter
normalization, and the installed finalization boundary remain assembler work.

## Verification

- 98 new core/composition/transport/boundary tests passed, including genuinely
  valid v1 operator receipts invalidated by a v2 declaration with unchanged PDF,
  Markdown, HTML and canonical bytes.
- 148 v1 composer, retained/localized/mobile/frozen export and installed worksheet
  tests passed.
- 132 v1 accepted-edition, reviewer/operator approval, operator delivery and
  Phase 4 authorization/delivery tests passed.
- A fixed baseline/candidate probe produces identical v1 PDF and ZIP hashes:
  PDF `0c88a10e944563af7007f0637a8d0db2635e0745fb20fa23db93121400685ee9`;
  ZIP `255fd66ec2b4cc742bcc6698861068dfea6c3f3d573ac2ed687a8995ac2200ab`.

Dense bilingual worksheet probes plus 65 retained primary pages preserve 105
source pages in two finished volumes of 60 and 47 pages (including new indices).
Composition, family construction, ZIP serialization and complete ZIP revalidation
took 1.040s EN / 1.053s es-MX; peak RSS was 102,700 / 105,132 KiB. Archives were
76,622 / 77,836 bytes and contained 12 members. These are synthetic local transport
measurements, not full installed rendering or production acceptance.

The core retains 60 pages per volume, 480 source pages, 512 total finished pages,
16 volumes, 128 source sections and 4 MiB aggregate input/output PDF bounds.
Transport permits at most 4 MiB combined text exports and 8 MiB for the complete
uncompressed family and archive. Core time checks remain cooperative: hard worker
time/memory limits and full-path profiling are prerequisites to endpoint activation.

## Remaining shipping work

Installed assembly must replace the single-PDF finalization/rebinding branch with
a complete-family acceptance/freeze boundary; otherwise old wrappers may drop
volumes or stale their hashes. Frozen/localized retrieval and UI must expose the
complete family. Reviewer and operator approvals, accepted editions, certificates,
delivery authorization and approved ZIP validators must then bind the same complete
manifest. Current v2 rejection guards stay until those replacements are tested.
No claim of customer-ready or production-retained-report success is made here.
