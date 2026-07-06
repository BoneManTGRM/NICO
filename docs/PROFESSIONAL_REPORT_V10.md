# Professional Report v10

This update targets the client-facing NICO Express PDF.

## Problems addressed

- Raw HTML break text appearing in PDF metadata.
- Page 2 containing only a small leftover scorecard block.
- Oversized scorecard cards causing awkward page breaks.
- Section headings being visually separated from their opening summary.
- Header looking more like a raw diagnostic export than a paid technical audit.

## PDF layout changes

- Dark professional NICO hero header.
- Clean metadata table for repository, client, project, and generated timestamp.
- Compact metric cards for maturity, score, confidence, and delivery verdict.
- Compact scorecard table instead of large stacked cards.
- No forced page break between scorecard and detailed sections.
- Detail sections keep each heading, summary, and Evidence label together, while long evidence/finding lists may split naturally.
- Footer remains evidence-bound and human-review gated.

## Safety and truthfulness rules retained

- Human review remains required.
- Missing evidence remains visible.
- No unavailable evidence is invented.
- PDF still omits long evidence lists and directs users to Markdown/HTML for full detail.

## Next report-accuracy work

The visual polish does not by itself change security or dependency scoring. Follow-up work should classify secret/static-analysis findings by source type so scanner-rule definitions, backend token variable names, docs examples, and test fixtures do not score the same as confirmed production risks.
