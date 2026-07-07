# Audit Evidence v18

This update adds concrete CI artifact collection for the next score increase.

## Added evidence collection

- Python dependency audit output is collected in NICO CI.
- Frontend npm audit output is collected in Node.js CI.
- A dedicated Audit Evidence workflow collects both Python and frontend audit artifacts.

## Why this matters

The report score cannot honestly rise much more from interpretation changes alone. The next gains need direct pass/fail evidence from CI artifacts and scanner outputs.

## What this does not claim

- It does not claim the repository is dependency-clean.
- It does not claim the repository is secret-clean.
- It does not remove human review.
- It does not hide unavailable evidence.

## Next scoring step

After audit workflows have successful runs and artifacts, NICO can use those artifacts as direct evidence in Express reports. That is the path toward moving Dependencies and report confidence higher without fake score inflation.
