# Deeper complexity engine

Update 5 adds worker-backed complexity evidence to move NICO closer to a real Express audit backend.

## What the engine analyzes

When the hosted scanner worker checks out an authorized repository, NICO now builds a `nico.complexity.v1` artifact with:

- source-file footprint
- source LOC
- Python AST function, class, import, call, and cyclomatic estimates
- TypeScript/JavaScript function-like, import, call, and branch estimates
- call-graph edge count
- hotspot scoring
- git churn signals
- ownership concentration signals
- manifest dependency count
- external import count

## Report attachment

The complexity artifact is attached to the hosted Express result as `complexity_engine`.

The post-processor applies it to:

- `Architecture & Technical Debt`
- `Velocity / Complexity`

If complexity evidence is present, NICO removes the old unavailable note for call-graph and cyclomatic complexity analysis. It keeps human-review limits where business context, story-point expectations, stakeholder input, or final client interpretation are still required.

## Scoring behavior

The engine returns:

- `complexity_score`
- `architecture_score`
- `velocity_score`
- `risk_level`
- `hotspots`
- `findings`
- `evidence`

Low and medium complexity risk can lift Architecture and Velocity/Complexity confidence. High complexity risk can cap those sections instead of hiding delivery risk behind a green score.

## Human review boundary

This is still not a replacement for a senior engineer review. It is evidence collection and first-pass triage. Final client claims still require human review, especially for high-churn files, highly concentrated ownership, high cyclomatic complexity, and large dependency surfaces.
