# Reparodynamics Engine

NICO now attaches a small repair-loop metric package to guarded report outputs.

The loop is:

Detect -> Classify -> Prioritize -> Repair Plan -> Approval -> Verify -> Trend -> Stabilize

Current metrics:

- detection_strength: fraction of required evidence sources that are verified.
- unavailable_evidence_burden: how much missing evidence remains.
- repair_pressure: how many sections still need repair or stronger evidence.
- stabilization_score: a conservative score that improves when evidence is verified and unresolved pressure falls.

These metrics do not claim that every bug was found. They measure whether the report has enough verified evidence to support stronger claims and where the next repair/evidence cycle should focus.
