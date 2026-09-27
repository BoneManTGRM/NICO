# Exact final-PDF availability correction

The live authenticated review for the actual failed run loaded revision 67 and retained artifact digests, but the supported download action found no final PDF payload. This is not evidence that the referenced PDF bytes were recovered or that final generation completed.

The API deliberately exposes final report bytes only after terminal stage, identity, locale and integrity checks. Review identity may also describe earlier retained report stages. The UI previously announced final-report availability unconditionally and enabled download based on a digest alone.

The correction requires the final PDF payload and a valid exact digest for the embedded download/approval workflow. Existing exact-byte verification still runs before download. Both supported languages now disclose unavailable final output. No fallback to an intermediate PDF, changed backend acceptance rule, approval or delivery is introduced.

Verification and independent review are in verification.json. The prior real failure remains open: this correction does not generate or recover the missing final PDF. Authenticated exact-input replay, resulting EN/es-MX inspection and final integration remain acceptance gates. The owner explicitly authorized completion and merging of both PRs when ready on September 26; no merge or deployment has occurred.

## Existing metadata contract alignment

CI push36246530946 on6a8cebdd failed one assertion in
test_final_report_independent_metadata_v1.py: it still matched the old
digest-only download guard. Local reproduction:12passed/1failed. The two
button-expression assertions now include finalPdfAvailable while retaining
operator authority, explicit acknowledgement and exact-download requirements
for approval, and no reviewer-metadata/acknowledgement gate for review download.
No production behavior or other assertion changed. Focused verification:28passed,
including the actual frontend handler suite wrapper. The full frontend suite
inside that wrapper passed70cases. Historical CI failure remains a failure.
