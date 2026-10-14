# Eleven exact reviewed source-hash observations

PR1729 head273790634874448932e276be7a5960ee93e1e7bf Security Audit Evidence run38571077016 retained37 Gitleaks findings and blocked on11. Official Gitleaks8.30.1 was verified against its published checksum and workflow pin551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb before local execution. The unchanged workflow command with its full fetched-head/tag scope reproduced37/11. The initial limited-ref checkout produced9/0 and was not treated as CI reproduction. No artifact/Library denied route was retried.

The eleven exact redacted shapes are retained in tests/fixtures/security/native_source_hash_observations.json. Secret was literally REDACTED and Verified absent in every observed record. Three matches on each owned_regressions.py:21 share a fingerprint: distinct Match/column pairs are required. All originating commits lie outside ordinary PR ancestry, retained by diagnostic/native-stage-counter refs.

## Source provenance

Ten literals equal previously independently derived source-file digests in commit6eff8889db11a3ab31c3b04f5af053edb542d6e8, docs/evidence/cppcheck-composed-runtime-20261012/fixed-final-source-sha256.json. Exact equality was checked with AST literal parsing, without importing or executing paused scripts. See docs/evidence/security-audit-cpp-source-digests-20261012.md for original pinned-source derivation and receipts. They are tokenizer/token/tokenlist source digests, not credentials.

The last observation is c2b3ba6045f2b3751108a40f95677c8e9d8c50cc:scripts/native_stage_counters/binding.py:12. Existing hosted run38463143379/job115523198616 log timestamps2026-10-13T20:32:56.9132861Z and20:35:00.7464353Z record overlay tokenizer before/after digests and candidate_source_sha256/lib/tokenize.cpp matching the exact source constant. Executed merge4f2a0197b4127283434ca7f63ed45a5d4a0ce2dd build.py:94–113 recomputed the candidate digest from copied stopped-container source bytes. instrument.py/binding.py/build.py blobs match head ebb72ca; tokenizer transformation body is byte-identical to c2b3ba, digest/insert/strip helper ASTs match. Independent reviewers and implementation agent verified this existing evidence separately. Build-and-bind succeeded; the overall historical job failed later. No qualification pass or fresh native execution is claimed.

Baseline run38399568855 passed with26/0 before the divergent finding commits' recorded creation times. Current full-ref scan includes those later histories. Prior PR source tree equals current main; identical source trees do not imply identical all-ref histories.

## Exact disposition and verification

Owner explicitly approved these eleven source-hash dispositions on2026-10-14. Existing approved_public_source_hash mechanism now recognizes only their exact commit/path/rule/redacted context/fingerprint/line/column fields with strict types. For these eleven, any present Verified field is rejected, including false/null/zero; absence is not coerced. Scanner scope/configuration, thresholds and history are unchanged. Counts, artifacts, human review and delivery restrictions are retained. No blanket hash/path/commit exception exists.

Regression before implementation:2 failed,319 passed (new focused selection). After implementation:651 passed across security_audit_gate, pr1641/pr1644 deployment and secret-capture modules. Tests reject changed/missing fields, wrong types, consistent unknown-commit fingerprints, unredacted and mixed records. Retained full report replay:37 findings,0 blockers,19 approved public source hashes (eight preexisting plus eleven newly approved); raw report bytes unchanged. No needless new scanner run.

Existing record data remains retained in replay.json. These results do not assert hosted CI success until the new exact commit completes CI. No merge, deployment, spending, C++ execution or history rewrite performed.
