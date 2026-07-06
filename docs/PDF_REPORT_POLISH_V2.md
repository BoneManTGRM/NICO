# PDF report polish v2

This pass improves the Express assessment PDF so it reads better on mobile PDF viewers and looks less like a raw export.

## Changes

- Uses a centered NICO / Reparodynamics branded header.
- Reduces the title size so it does not visually crop or dominate the page.
- Replaces wide score tables with stacked section cards.
- Keeps the scorecard single-column and easier to read on small screens.
- Reduces evidence list length in PDF while leaving Markdown/HTML available for full details.
- Adds clearer section separators.
- Reduces orphaned section headings by keeping headings with first content where practical.
- Keeps unavailable evidence and human-review warnings visible.

## Accuracy boundary

PDF polish does not change assessment scoring. It only changes presentation. Missing evidence remains disclosed, and client-facing delivery still requires human review.
