# Audit Changelog

## Evidence health reconciliation v1

- Prevent false `No scanner failure` summaries when canonical findings retain failed or incomplete scanner evidence.
- Preserve structured scanner execution records as the preferred source.
- Add finding-derived fallback limitations with explicit provenance.
- Keep required/non-required classification separate.
- Add focused regression coverage.
