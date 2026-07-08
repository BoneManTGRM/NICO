# Release readiness API route

This update adds a route registrar for release readiness.

Endpoint:

`POST /release/readiness`

Module:

`nico/release_readiness_api.py`

The route returns a structured readiness artifact from a supplied payload. It does not perform external calls.
