# Invocation-local exact-artifact digest reuse

Base: `fa9d0fa64da44cbe73cf0f2c3de73071162666d5`.
Reviewed implementation SHA-256: `65bb0f4356c82c5a807ed4bc9107da82d572648e0ac7e69face72163f71a59a5`.

The manifest loop already verifies each artifact's digest and byte count. The later draft-identity check previously encoded/decoded and hashed canonical JSON/PDF again. The change reuses those observed digests only when the later source is the identical built-in immutable string. Receipts bind to the actual single-read extraction value, are private to one invocation, and are never caller supplied. Fallback consumes its captured value without another mapping lookup. Non-string provenance is discarded and conversion temporaries are released at the conversion boundary. All current claims, mutable structures, identity, lifecycle and approval checks remain.

## Verification

- Python 3.12.14: **152 passed** (22 regression cases plus 130 compatibility cases).
- Python 3.11.17: **152 passed**, same seven files in isolated processes, existing offline container with read-only source/root, non-root user, no network and bounded resources.
- **50 exact baseline comparisons** matched results, exception messages and explicit causes.
- Regression controls reproduce two accepting ABA failures in the rejected pre-read/post-read proposal and two lifetime failures in the earlier single-read revision; final code rejects correctly. Four lifetime cases are retained in repository tests.
- Parent confirmed independent bounded review of the exact implementation digest, including both ABA cases, four lifetime cases and 40 earlier controls.

`verification.json` contains per-file summaries. Each test file was run separately with `python -m pytest -q tests/test_<name>.py`; this preserves the established isolation for process-global report installers. No production retrieval, assessment, settings change or deployment was used for verification.

## Fixed-condition component benchmark

`benchmark.json` retains samples. A real manifest fixture augmented with 40,000 synthetic evidence rows produces 46,568,423 canonical JSON bytes (digest recorded in JSON). It is not a production record. Two complete package validations per sample include helper/receipt overhead, identity guards, active timing aggregation and file logging. Python 3.12.14; one CPU affinity; GC enabled; six samples per variant in ABBA order repeated three times; warmup/correctness first. Fixture setup excluded equally; allocation measured separately.

| Measurement | Base | Candidate |
|---|---:|---:|
| Median wall time | 584.821967 ms | 503.2948135 ms |
| Median CPU time | 584.319528 ms | 502.938632 ms |
| Peak additional allocation | 195,813,961 bytes | 149,247,829 bytes |

This is a 13.94% local component reduction, not a production download speedup or sub-10-second result. Record decoding and record-integrity hashing are unchanged. Hosted exact-head CI remains a separate gate. Full local harnesses, phase logs and negative-control evidence are retained in `/workspace/single-read-artifact-digest-review/lifetime-final/` and its parent directory.
