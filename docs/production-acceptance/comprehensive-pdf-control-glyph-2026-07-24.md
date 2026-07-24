# Comprehensive PDF control-glyph acceptance failure

Date: 2026-07-24

Production acceptance run: 30100505111

Release commit: `1347968fde9f44e7a0929ce57e79a8cbf0c0bfdf`

Comprehensive run: `comprun_f9617c5fc97b41ba83dc4f72ecf54399`

Observed failure:

`Comprehensive PDF contains a control-character glyph`

The generated report completed all automated Comprehensive stages and reached the required human-review gate. The acceptance runner rejected the PDF because `pypdf` extracted ReportLab Helvetica list bullets as DEL (`U+007F`). The affected text was list content in the technical sections and evidence appendix, not a scoring, scanner, run-identity, or delivery-authorization failure.

Repair boundary:

- Replace PDF-only bullet prefixes with ASCII `- ` markers in both the premium report body and decision-grade appendix supplement.
- Preserve the report text, technical scores, assurance values, evidence, exact run identity, human-review requirement, and blocked client delivery.
- Add PDF extraction regression tests that reject `U+007F` and verify list content remains readable.
