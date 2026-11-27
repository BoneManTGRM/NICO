"""CI-only verification of the installed TypeScript scanner and normal retention."""
from __future__ import annotations

import gzip
from hashlib import sha256
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from nico import nico_ci_typescript_typegen_inputs_v1 as pin
from nico import scanner_evidence_pipeline_v1 as pipeline
from nico.worker_execution import WorkerWorkspace


def main() -> None:
    with TemporaryDirectory() as tmp:
        workspace = WorkerWorkspace(Path(tmp))
        shutil.copytree(Path("/reference/repo"), workspace.repo_dir, symlinks=True)
        prove(workspace)


def prove(workspace: WorkerWorkspace) -> None:
    typescript = next(spec for spec in pipeline.TOOL_SPECS if spec.name == "typescript")
    artifact = pipeline.run_canonical_scanner_tools(workspace, specs=(typescript,))
    native = artifact["tools"]["typescript"]
    if (native["status"] != "completed" or not native["verified_for_this_report"]
            or native.get("execution_source") != "owned_confined_native_typescript"
            or native.get("source_checkout_verified") is not True):
        raise SystemExit("Installed TypeScript did not provide fresh exact native evidence: " + str(native.get("reason")))
    with TemporaryDirectory() as root:
        stored = Path(root)
        fixture_run = "ci-typecheck-integration-proof"
        pipeline.materialize_raw_artifacts(
            artifact, stored, repository=pin.REPO, commit_sha=pin.HISTORICAL_COMMIT, run_id=fixture_run,
        )
        record = artifact["raw_artifacts"]["typescript"]
        path = stored / record["storage_key"]
        raw = gzip.decompress(path.read_bytes())
        observed = json.loads(raw)
        if (fixture_run not in path.parts or pin.HISTORICAL_COMMIT not in path.parts
                or sha256(raw).hexdigest() != record["sha256"] or observed.get("commit") != pin.HISTORICAL_COMMIT
                or observed.get("tree") != pin.HISTORICAL_TREE):
            raise SystemExit("TypeScript native retention did not bind the exact fixture run")
    print(json.dumps({
        "native_typescript_verified": True,
        "retention_bound_to_fixture": True,
        "genuine_assessment": False,
        "compiler": native["scanner_tool_version"],
        "target_commit": pin.HISTORICAL_COMMIT,
        "roots": native["native_typecheck_root_count"],
        "program_files": native["native_typecheck_program_file_count"],
        "compiler_reads": native["native_typecheck_read_file_count"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
