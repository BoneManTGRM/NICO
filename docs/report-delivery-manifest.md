# Report delivery manifest

This update adds `nico.report_delivery_manifest.v1`.

The manifest combines report delivery readiness, final review, client acceptance, and evidence bundle status into one delivery go/no-go artifact.

The manifest checks:

- delivery readiness
- final review approval
- client acceptance approval
- evidence artifact bundle presence

The output includes delivery status, allowed flag, missing evidence, blockers, next action, and human review requirement.
