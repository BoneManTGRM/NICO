# Phase 12C — Production Evidence Manifest

This phase converts production release evidence into a deterministic, machine-checkable manifest.

## Required release identity

Every manifest must bind all evidence to one immutable commit SHA and identify the environment, assessment tier, locale, format, deployment identity, artifact identity, and SHA-256 digest.

## Fail-closed conditions

Release certification fails when any required tier, locale, or format is absent; when staging or production is unhealthy; when deployment SHAs diverge; when verification passes do not share the exact SHA; when artifact identities or checksums are incomplete; when smoke, mobile-download, or manual-inspection evidence is missing; or when critical/high defects remain open.

## Product surface

The required matrix is Express, Mid, and Full across English and Spanish, with PDF, HTML, and Markdown artifacts for each combination.
