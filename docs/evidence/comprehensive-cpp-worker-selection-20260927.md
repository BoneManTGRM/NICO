# Comprehensive C++ worker selection repair

Base: `2d9856bef72d19927b75c63b06eb3e88e417da9e`.

The live Comprehensive provider did not invoke the existing release-owned
configure-first selector. The separate snapshot assessment handler did. Thus
even qualified deployment settings could not attach the C++ child to a new
Comprehensive scanner run.

The repair supplies the selector with the retained completed repository stage
and immutable snapshot. Only its accepted internal contract reaches the existing
scanner entry point. Existing scanner IDs are loaded without reselection or
dispatch. No deployment settings, qualifications, limits, findings, approval
rules, or report-delivery rules change.

## Verification

The installed v5 Comprehensive provider was exercised with the real selector;
only the scanner enqueue boundary was substituted. On unchanged source, the
two eligible C++ cases failed because no child contract was passed, and the
12 negative/preservation cases passed. After repair all 14 passed.

Focused selection and production binding: 24 passed. Broader affected checks:
85 passed, zero failures or skips. Existing pypdf and Starlette deprecation
warnings remain. The commands were:

```sh
python -m pytest -q tests/test_comprehensive_cpp_worker_selection.py tests/test_cpp_production_selection.py tests/test_comprehensive_native_production_binding.py
python -m pytest -q tests/test_comprehensive_cpp_worker_selection.py tests/test_cpp_production_selection.py tests/test_cpp_configure_first_contract.py tests/test_cpp_configure_first_projection.py tests/test_assessment_required_tools.py tests/test_comprehensive_native_production_binding.py tests/test_comprehensive_native_provider_access_binding.py tests/test_comprehensive_scanner_stage_wording_v1.py tests/test_private_snapshot_scanner_auth.py
python -m compileall -q nico/comprehensive_native_providers.py tests/test_comprehensive_cpp_worker_selection.py
git diff --check
```

## Production observations and remaining work

Authenticated NICO recovery showed the preserved Bitcoin run
`comprun_bb3c46357f72a5f04f93264ffa1316ff` blocked at 13.04%, with
`snapshot_scanner_not_verified`, against commit
`ed7dd7cf4e1561a97edf72eba29a67b14e28c717`. The retained scanner inventory
could not verify its source binding. The interface did not expose the
underlying checkout failure; this patch is not proof of that failure's cause.

Railway's fully rendered variable-name inventory showed the C++ enablement,
dispatch enablement, image config ID, qualified release, qualification run,
qualification artifact hash, and worker repository ID settings absent.
Deployment `d767cd6b-468c-48bb-9e2a-f8ca349464d8` was successful, but that
does not establish activated C++ execution.

The independently prepared image-qualification work in the existing workspace
was preserved. This repair was made in a separate worktree. Production image
qualification/publication, release-aligned activation and dispatch, and a fresh
live completed Bitcoin report remain unverified. The preserved failed run was
not retried or changed, and no client approval or delivery was performed.
