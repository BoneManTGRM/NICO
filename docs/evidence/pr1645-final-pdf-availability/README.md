# Exact final-PDF availability correction

The live authenticated review for the actual failed run loaded revision 67 and retained artifact digests, but the supported download action found no final PDF payload. This is not evidence that the referenced PDF bytes were recovered or that final generation completed.

The API deliberately exposes final report bytes only after terminal stage, identity, locale and integrity checks. Review identity may also describe earlier retained report stages. The UI previously announced final-report availability unconditionally and enabled download based on a digest alone.

The correction requires the final PDF payload and a valid exact digest for the embedded download/approval workflow. Existing exact-byte verification still runs before download. Both supported languages now disclose unavailable final output. No fallback to an intermediate PDF, changed backend acceptance rule, approval or delivery is introduced.

Verification and independent review are in verification.json. The prior real failure remains open: this correction does not generate or recover the missing final PDF. Authenticated exact-input replay, resulting EN/es-MX inspection and final integration remain acceptance gates. The owner explicitly authorized completion and merging of both PRs when ready on September 26; no merge or deployment has occurred.
