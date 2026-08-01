# Remediation scope

The production defect addressed here is not that the repository suddenly became materially worse. The defect is that unverified scanner candidate volume was being subtracted from technical scores, `completed_with_findings` was treated as incomplete execution, duplicate exact-source findings were rendered as separate risks, and stale score aliases could produce blocked report contracts after otherwise valid scoring.

This change preserves genuine penalties for verified material findings, missing lockfiles, incomplete applicable analyzers, and measured architecture complexity. It does not alter the architecture score, remove human review, authorize client delivery, or use a target score as an input.
