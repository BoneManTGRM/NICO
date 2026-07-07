# Report Finalization v17

This update fixes why some NICO Express reports only moved slightly after scoring work.

## Problem

The hosted Express endpoint generated polished report output before the final accuracy pass. That meant the PDF/report layer could show older score interpretation even after accuracy classification ran.

The confidence engine also treated unavailable stronger scanners as missing required evidence even when hosted evidence already satisfied the required evidence category. That was too conservative for provisional hosted scoring.

## Changes

- Runs hosted assessment first.
- Attaches worker evidence when available.
- Enriches scanner evidence.
- Applies report accuracy classification.
- Finalizes/polishes the Express result last so the PDF and displayed score reflect the final interpreted evidence.
- Changes required-source confidence logic from `required & unavailable` to `required - evidence`.
- Keeps unavailable scanner evidence visible as optional-unavailable evidence when hosted evidence exists.

## Expected effect

Reports should move more when low scores are caused by false-positive interpretation or broad hosted warnings. Stronger scanners are still shown as unavailable, but their absence no longer automatically suppresses a section when hosted evidence already supports the provisional score.

## Safety rule

This does not claim scanner-clean status. Human review remains required, and unavailable evidence remains visible.
