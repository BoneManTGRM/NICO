# Evidence artifact bundle

Update 6 adds a report-safe evidence bundle for hosted Express assessments.

## Purpose

The Express report should be defensible. A client-facing PDF is not enough by itself. NICO now creates a JSON-native evidence bundle that records the rendered artifacts, raw evidence, scanner summaries, hashes, timestamps, CI references, and unavailable-data inventory.

## Bundle schema

The bundle uses:

`nico.evidence_bundle.v1`

It includes:

- Markdown report hash
- HTML report hash
- PDF hash and byte count when PDF export is available
- raw evidence JSON hash
- scanner outputs JSON hash
- unavailable inventory hash
- bundle hash
- creation timestamp
- repository and assessment metadata
- human-review requirement

## Raw evidence JSON

The raw evidence object includes:

- repository metadata
- maturity signal
- maturity semaphore
- scored sections
- findings
- repair recommendations
- quick wins
- medium-term plan
- resourcing recommendation
- risk register
- verification checklist
- scanner outputs
- unavailable data notes
- safety boundary

## Scanner outputs

The scanner-output section includes report-safe summaries for:

- scanner-worker artifact
- complexity engine
- Bandit triage
- full git-history secret scan metadata

It does not expose raw secret values.

## Unavailable inventory

Every unavailable-data note from sections and global report metadata is collected into a single inventory so a reviewer can see exactly what was not verified.

## Human review

The bundle makes the report more defensible, but it does not remove the human-review requirement. Final client delivery still needs approved review and signoff.
