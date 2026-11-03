# Retained advisory explicit-version evidence v1

Local stacked change on PR1874 head16bf4f499e42668c65bd8f11afe00e7a3e0c94c0. It reports only that a retained advisory explicitly lists a qualified locked version. It never writes installed_version_affected, resolution-fixed, reachability, dispositions, scores or approval flags.

## Evidence path

The existing snapshot worker persists scanner original bytes before candidate capture. This addition consumes that already retained in-memory OSV result. It checks exact run/repository/customer/project/commit binding, expected scanner artifact ID, original raw checksum reference, durable-retention flags, successful complete-capture metadata and the existing result-integrity hash. It reads no artifact store and invokes no scanner/network/dependency command. Integrity hashes bind trusted server persistence; they are not cryptographic advisory publisher authentication.

One complete OSV result and at most128 findings are supported. Missing flags, partial/timed-out/failed results, malformed findings, multiple OSV results and truncated candidate populations yield no proof. Preview truncation alone does not mean raw-file parsing was incomplete: the existing complete-capture flag remains required. Older OSV fallback shapes missing output_limit_exceeded remain unsupported.

Only one affected entry with the minimal exact npm package name/ecosystem object and a nonempty unique explicit list of at most256 bounded semantic-version-shaped strings is accepted. Range-only records, aliases, multiple entries, malformed lists, withdrawn advisories and nonmatching strings yield no positive proof. No range engine, semver ordering, advisory freshness claim or negative unaffected result is introduced. Optional additional package fields currently fall outside this deliberately narrow shape.

Qualified locked identity is mandatory. Conflicting same-claim records are suppressed independently of occurrence order. The receipt includes the exact advisory ID, locked package/version, selected-fields hash, scanner result/raw references and lockfile hash, plus explicit unknown installation/affectedness/reachability. It does not retain advisory prose, URLs or version lists in the client packet. GET projection rechecks the independent retained observation and exact receipt; arbitrary embedded receipts cannot qualify themselves. UI retains canonical index/fingerprint association and all installation/advisory/runtime questions in English/es-MX.

## Bounds

Ordinary JSON preflight precedes result escaping/hashing: maximum32depth,8192nodes,16KiB/string and conservative escaped-size upper bound1MiB. Serialization polls the existing cooperative deadline. The capture shares the five-second deadline,8MiB aggregate input and2MiB retained output; advisory input bytes are charged before Git blob reads. Advisory capture is at most256KiB. Investigation and display share the existing256KiB identity-receipt allowance with advisory receipts rather than adding another allowance. No whole-assessment hard resource guarantee follows.

## Validation and limits

Synthetic cases cover positive/nonmatching/foreign package/ecosystem, missing/range-only/malformed/duplicate lists, conflicting revisions, wrong source scope, tampered integrity, missing/contradictory capture flags, oversized/deep/node-heavy input, deadline exhaustion, malformed/129-row populations, injected persisted receipts, absent locked identity and shared output budgets. A generated local Git repository proves actual capture-to-persistence projection without network or database. Existing candidate, finalization, score-truth and capture regressions remain unchanged. Bilingual component tests retain pending disposition questions and suppress stale/foreign proofs.

Earlier failed experiments are retained: preflight initially allocated escaped large strings before checking size; independent review required structural preflight. Four tests then exposed preflight ordering before artifact-ID serialization, and one synthetic integration fixture omitted category; corrected without weakening assertions. Broader regression caught an unnecessary clock read on non-advisory rows; guarded receipt-specific deadline checks restore compatibility. No production efficacy, installed affectedness, calibrated score, browser-layout qualification or candidate-resolution improvement is claimed.
