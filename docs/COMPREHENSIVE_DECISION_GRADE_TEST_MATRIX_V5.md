# Comprehensive Decision-Grade v5 Test Matrix

Required regression coverage:

1. Score 92 maps to Exceptional while yellow evidence maps to Review Limited.
2. Dependency and static candidates do not appear in Secrets Exposure Review.
3. Unavailable Gitleaks or TruffleHog produces a coverage limitation, not a verified exposure.
4. Measured architecture hotspots appear with path and complexity.
5. Production bootstrap installs the v5 binding before native providers.
6. Human review remains required and client delivery remains disabled.
7. The stable report import surface resolves successfully.
