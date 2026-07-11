# Full-run report quality plan

The full-run page is now visible, but Express PDF output and full-run output are still separate paths.

Next implementation target:

1. Promote full-run report output from an internal progress view into a client-readable report package.
2. Keep Express PDF wording explicit so users know it is the fast Express path.
3. Preserve human review and approval gating before client delivery.
4. Show the report path used in every generated result: `express` or `full_run`.
5. Add tests so the UI cannot silently label an Express report as a Full Assessment report.
