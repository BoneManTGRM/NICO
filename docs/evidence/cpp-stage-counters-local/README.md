# Current-only stage counters: local integration review

See INTEGRATION-PLAN.md for the full isolation policy and proposed hosted command. All changes are diagnostic-only, based on1960abf2b29bd87940567396203f09d128132aae. Production collector, production Dockerfile, all qualification filters and the separately held scheduling correction are unchanged.

## Measurement

Activation requires an validated diagnostic binding from the trusted workflow and the exact environment value NICO_CPP_STAGE_COUNTERS=1 at the analyzer subprocess boundary. Numeric fixed-size saturating counters report template pass, using call, alias scan, whole-list/prelude/inner token visits, scope nodes, match/base/scope queries, RHS distance calls and reused distance totals, RHS parse entries, substitutions and successful template-instantiation calls. No new traversal, cache, index, semantic limit or signal handler is added.

NICO_STAGE_V1 fields: process-global sequence,event(0sample/1entry/2exit),kind(1template/2using/3alias),lane,wall_microseconds,process_CPU_ticks,CLOCKS_PER_SEC; followed by the ordered fields in evidence.FIELDS. Counters are cumulative per lane. Constructed child nodes exclude roots/copies; substitution counts are operations, not inserted-token counts; instantiation counts are successful declaration calls, not all generated templates.

The first entry of each kind may bypass throttling; later events are globally rate-limited to one/second. Hot-loop sampling occurs every4096 counter operations. Output caps128records,1024bytes/record; the existing collector's64KiB output cap remains unchanged. Later entry/exit transitions may be omitted. Long work without callbacks can leave stale snapshots. These identify latest observed activity, not a precise termination hotspot. Flushed valid prefix records survive a truncated final line; malformed completed lines remain invalid. Outer collector failure retains completed case prefixes and native output hashes.

ScopeInfo3 grows during alias scans. Do not transplant immutable-helper caching. Any future optimization must preserve direct-child-first lookup, sibling namespace ordering, short/full-name matching, self exclusion, declaration-range mutation, and malformed/unused-alias diagnostic timing.

## Pinned source and new identities

Upstream: ac9db3069b9f90e81e126a090b99ad456e122cf8.
Original tokenizer SHA256:76beaa920046dbe057c5b20b09c043802351692657e2b3f269cf4612984eac88.
Original template-simplifier SHA256:61e6d1c8be0327fe8689c132b95ad519d95685e88d9766e8862e625b80e11d4f.
Header SHA256:924d2ad1ffd460fb894df6b493be029db2c1dd8b5b335f58bcdcbf69377f693f.
Overlay identity:4c82ebc973709634ad378c98ce0fd0c7fdfe4a73726b48503967de3c60319607.
Input bytes remain untouched; removing the inserted markers reproduces both pinned sources byte-for-byte. The original Cppcheck f5215e... and observer454746... remain the archive identities.

## Actual validation

145 Python diagnostic/source/environment/identity/evidence/static-stage contracts passed before final review. Negative cases include changed source/header/recipe/script, changed runtime image/binary/original-image, wrong binding seal, unsupported flags/commands, ambient opt-in and malformed/truncated evidence. Original static-stage contracts remain covered.

Owned two-translation-unit helper controls (separate authorization): GCC14.2.0 Debian14.2.0-19, -O2 -DNDEBUG -std=c++11 -pthread.131.236s total of180s. Strict opt-in/default silence, shared process output, independent lane counters, frame restoration,128-record cap and >=1second post-entry rate passed. Expected SIGKILL exit-9 retained three flushed entries; truncated captured bytes tested prefix retention. Short noisy helper timings are not analyzer-overhead evidence.

Authorized full trusted-analyzer compile only: existing pinned source and available dependencies, installed GCC14.2.0, make -j2 MATCHCOMPILER=yes FILESDIR=/opt/cppcheck CXX=g++-14 CXXFLAGS=-O2 -DNDEBUG. Exit0 in118.201738s against210s cap, no timeout. New local binary6855280bytes SHA256 ed79c96b90b246110b696290e580b555ffdc7438c6f6b878adc0bee48e9911c7. The analyzer was NOT executed.46 compiler warnings retained, including multi-character constants and ignored attributes; no build errors.

Compile resources: parallelism2; original source22843805bytes; build tree46848048bytes; stdout19461bytes/stderr6411bytes. CPU time, peak RSS and cgroup throttling were not collected, so no claims about those metrics. Compiler SHA2566b3696e4dcb85e1c949c732a02befa50e3983ecf94ce7e8e58d9d503b954b79d. Full logs/receipts remain under /workspace/nico-stage-full-build. No installs, services, Docker build, assessed execution or publication occurred locally. The local binary is not asserted equal to the future hosted binary or full worker.

## Remaining gates

Trusted capture plus consumer digest checks is workflow provenance, not independent hostile-host attestation. Parent review, fresh refs/full-delta path audit, provider-impact/budget checks and successful hosted owned controls are required before the proposed current-only run. Hosted image identity, actual collector integration, analyzer overhead and assessed behavior remain unverified. No timeout improvement, clean qualification or release readiness is claimed. Known remote scheduling-test failures remain visible.
