# Local integration and proposed hosted run

Status: implemented locally for parent review; no publication, dispatch, merge, deployment, or assessed execution. Original 34109-byte patch remains preserved separately (SHA256 5e290eb9c69fa0b47dd79b5c97692ed4098396be373a9b728d06cc2134f59e86). Integration base is 1960abf2b29bd87940567396203f09d128132aae. The scheduling-test correction at22ed9bb78128d42d65737dba00a1a4f4ca50e73c remains excluded; its remote CI failures remain visible.

## Activation and identity boundaries

Production collect_project_static constructs a fresh environment at assessment_cpp_project_static.py268–271 and copies it before analyzer _run. Docker environment alone is insufficient. Only the diagnostic primary_program wrapper adds exactly NICO_CPP_STAGE_COUNTERS=1 to a copied environment, for an exact approved analyzer argv reconstructed from the three validated retained contexts plus the existing --showtime=file and --report-progress=1 flags. The default path, version probe, production allowlist, header-provenance variable, request schema, flags, deadlines and serial scheduler are preserved. Ambient opt-in cannot activate the wrapper; unsupported commands/flags fail closed.

CURRENT_TOOLS, archive hash, retained-file/source/snapshot validators and compiler-environment comparison remain unchanged. A separate trusted capture step observes original and instrumented binary/observer hashes from stopped containers and validates the exact overlay and private recipe. It produces binding.json and a canonical binding digest. Consumers require that separately supplied digest, the original-build image ID, the instrumented image ID, the reviewed source/header/recipe/script hashes, fixed compiler/build flags and activation policy. The actual sandbox binary and observer hashes must then match. Both identity chains are retained. The digest provides integrity within this trusted workflow, not independent attestation against replacement of both binding and expected digest by a malicious host.

## Build and owned controls

The production Dockerfile is untouched. A diagnostic generator creates a private copy, adding the reviewed overlay after the existing source repairs and before the original -j2 MATCHCOMPILER=yes FILESDIR=/opt/cppcheck CXXFLAGS=-O2 -DNDEBUG build. It checks GCC14.2.0. The original image/receipts remain; the instrumented image has a new digest and an overlay receipt. Existing inner make180s and outer diagnostic build205s plus5s termination limits apply.

The workflow retains original owned-control-first ordering, then builds/binds the diagnostic image and runs owned analyzer environment controls before downloading retained assessed evidence or checking out Bitcoin. Those controls call the same environment adapter with false/true activation under an ambient opt-in, require disabled silence and enabled bounded numeric records, and verify runtime hashes. These hosted controls have not run locally: authorization covered compilation of the full analyzer, not its execution.

## Exact hosted route, after review only

Use existing stacked PR1727: head diagnostic/current-primary-38380333159, base repair/ast-boundary-independent-fc9a0a75-20261012, same-repository guard. Recheck exact remote refs before publishing. Preserve contents/actions read permissions; shared cpp-full-project-integration-refs/pull/1722/merge lock; queue:max; cancel-in-progress:false; job55min; producer run38380333159/head2bd1ea9 gate; artifact retention30days.

The dedicated scripts/native_stage_counters package and tests/test_native_stage_counters.py are diagnostic-only. They and the existing native_timeout_diagnostic script/test/workflow paths do not match the unchanged full-integration path filters. The entire PR delta must be rechecked against the live base, not only the incremental commit. No required check is disabled, weakened, spoofed or treated as passed. Future production changes still require their ordinary qualification gates.

Proposed hosted invocation:
python -m scripts.native_timeout_diagnostic --mode current-primary --archive retained-timeout.zip --archive-sha256 dbf890120e44a7d0f99133d69f316c9e8d7dce0210f3ae627e248ffa1c4e7e92 --qualification-source qualification-input --qualification-manifest tests/fixtures/cpp/bitcoin-configuration-benchmark.json --image <stage-image-id> --stage-runtime-binding native-diagnostic-evidence/stage-binding/binding.json --stage-runtime-binding-sha256 <trusted-capture-binding-digest> --original-image <original-build-image-id> --output native-diagnostic-evidence/isolated

The immutable archive remains artifact11811288494,22698583bytes. Frozen Bitcoin remains bb5296576e8f1a9fc11c19d9a25ba02ed4547e24. Only indices2/basic.cpp,4/bitcoin-node.cpp,10/compat/stdin.cpp run, serially, with90s/case and540s aggregate. Preserve4CPU/12GiB/256PIDs/9GiB scratch, no network, readonlyroot, capability/no-new-privileges policy, original output caps and cleanup. Retain unsuccessful cases, commands, wall/phase times, numeric counters, source/tool/image/binding hashes, raw output and unknown resource metrics. No baseline comparison or unchanged qualification rerun.

## Other effects and publication gates

A PR update still schedules unrestricted ordinary workflows: NICO CI, Two Service Production Acceptance contracts, Postgres Restart Proof, Mobile Restart Production Proof contracts, iOS WebKit Paint Proof contracts, Recorded Golden Demonstration, Resilience Proof, Frontend Production Release Proof contracts and Audit Evidence. NICO CI also triggers on push, so both events can schedule it. These perform ephemeral services, tests/builds, dependency/scanner work and artifact uploads. Main-only live proof jobs are not enabled by this stacked PR. External Railway/Vercel branch-preview/deployment effects cannot be proven from YAML: parent must recheck provider impact and remaining budget before publication. No provider authentication attempt was made.

Existing Remediation Evidence dispatch is still blocked by Forbidden; do not retry it or use this route for ordinary certification. No new main commit, platform deployment, production assessment, paid service or manual duplicate diagnostic is proposed.
