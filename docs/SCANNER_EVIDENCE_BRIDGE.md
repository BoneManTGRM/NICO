# Scanner Evidence Bridge

NICO report packages can now fold scanner-worker results into the same evidence-confidence and Reparodynamics scoring path used by report sections.

When a report payload includes `scanner_results` or `scanner_run.scanner_results`, NICO adds a `Scanner Worker Evidence` section.

Supported evidence groups:

- dependency_intelligence: pip-audit, npm-audit, osv-scanner
- static_analysis: semgrep, bandit, eslint
- test_execution: pytest, npm-test
- build_execution: npm-build

The bridge does not claim a repository is bug-free or safe. It records what scanners ran, what scanners failed, what scanners were unavailable, and which conclusions still require human review.

This improves accuracy by moving reports from generic scanner-unavailable language toward scanner-backed evidence when controlled worker output exists.
