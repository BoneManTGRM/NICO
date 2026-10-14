# Bounded visible source inventory previews

Parent's independent comparison found a PDF presentation regression: all 35
sections remained and detailed findings increased, but large source inventories
showed only counts/hashes. Original rows remained in canonical JSON. Parent's
current diagnostic PDFs were 52 pages in English and 56 in Spanish; those files
were not materialized or rerendered in this executor.

On main 15a9e948, four synthetic regressions failed because the summary branch
displayed no rows. The repair retains the same complete-table count, hash and
reference token, then displays the first 15 rows (24 for source interactions) in
original order. Small tables still display every row through the unchanged
48-row threshold. Generated coverage/limitation tables remain complete.

Both languages disclose shown/total counts, omitted rows and cell truncation.
Preview cells are localized, whitespace-normalized, limited to 80 characters
including a visible ellipsis, and escaped before ReportLab wrapping. This is an
explicit display tradeoff, not a claim that every long cell is fully visible.
Full canonical values, row order, table hashes and complete Markdown remain
unchanged. No page limit, deadline, score, finding, approval or delivery gate changed.

Representative nonsensitive fixtures contain 2,499 components and 21,802
interactions. Exact visible counts are 15 and 24 in both languages; repeated
invariant renders are byte-identical. Standalone previews use two pages per
language for representative cells and four for 4,000-character pathological
paths/targets. These are standalone layout measurements, not predicted page
counts for the authentic reports. The existing composer preserves preview rows
and required pages at 60 pages and rejects a 61-page fixture; it does not silently
reduce previews or drop other sections to make room.

Tests also bind the actual preview PDF to the complete canonical export and
verify unchanged canonical digest, synthetic scores/findings and pending approval
with delivery blocked. Independent read-only review found no blockers and passed
25 checks before the two additional canonical-export preservation cases were added.
Final focused verification passed all 210 tests across source presentation/export,
architecture evidence, PDF composition, register conservation and finding references.

Production-size/authentic PDF visual and page-budget acceptance remains with the
parent. If the combined report exceeds the existing 60-page boundary, it must
remain blocked; no fit is inferred from these synthetic previews. No production
input transfer, assessment, workflow dispatch, merge or deployment was performed.
C++ remains paused and the database pilot remains on HOLD.
