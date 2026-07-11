# Report path labels

NICO now separates report origin explicitly:

- `report_path: express` means the output came from the fast Express Assessment path.
- `report_path: full_run` means the output came from the Full Assessment orchestrator path.

This prevents an Express PDF/report from being mistaken for Full Assessment output.

Client delivery still requires human review and approval regardless of report path.
