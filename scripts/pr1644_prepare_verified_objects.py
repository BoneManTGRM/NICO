"""One-use, data-only Git object preparation; never updates a ref or executes NICO."""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request

REPOSITORY = "BoneManTGRM/NICO"
BRANCH = "fix/cpp-runtime-scratch-retention"
BASE = "937ce8345286c5bf4557497a260580cbb2a53d8e"
BASE_TREE = "b5c49087af64fd2df9130989e9f6da99f8dd5251"
DATA = "docs/evidence/pr1644-object-publication-20260925"
HELPERS = sorted([
    ".github/workflows/pr1644-prepare-verified-objects.yml",
    "scripts/pr1644_prepare_verified_objects.py",
    DATA + "/verified.patch",
    DATA + "/manifest.json",
])
ALLOWED = sorted([
    "nico/assessment_cpp_configure_first_projection.py",
    "nico/assessment_cpp_full_project_report.py",
    "nico/assessment_cpp_runtime_execution.py",
    "nico/comprehensive_client_review_companion_v2.py",
    "nico/comprehensive_spanish_canonical_report_v87.py",
    "tests/test_cpp_configure_first_projection.py",
    "tests/test_cpp_functional_failure_prefix.py",
    "tests/test_cpp_retained_compressed_identity.py",
    "NICO-Ship-Checkpoint.md",
    "docs/evidence/pr1644-integrated-corrections-20260925/verification.json",
])
MANIFEST_SHA256 = "c09b0f15285985328203f7c42af4b88ad62151513d9572b21cbcdbb73e35b2a3"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def blob_id(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args],
                          check=check, capture_output=True, timeout=30)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("GitHub API redirect rejected")


def api(method: str, endpoint: str, payload=None):
    # Write capability is deliberately restricted to immutable object creation.
    require((method == "POST" and endpoint in {"git/blobs", "git/trees"}) or
            (method == "GET" and endpoint == "git/ref/heads/" + BRANCH),
            "API operation is outside the object-only allowlist")
    raw = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.github.com/repos/" + REPOSITORY + "/" + endpoint,
        data=raw, method=method, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + os.environ["NICO_OBJECT_TOKEN"],
            "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28",
        })
    with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
        body = response.read(8 * 1024 * 1024 + 1)
    require(len(body) <= 8 * 1024 * 1024, "API response exceeds bound")
    return json.loads(body)


def prepare() -> dict:
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY and
            os.environ.get("GITHUB_REF") == "refs/heads/" + BRANCH and
            os.environ.get("GITHUB_EVENT_NAME") == "push", "Wrong repository, ref, or event")
    head = os.environ.get("GITHUB_SHA", "")
    require(re.fullmatch(r"[0-9a-f]{40}", head) is not None, "Invalid input commit")
    require(git("rev-parse", "HEAD").stdout.decode().strip() == head, "Checkout mismatch")
    require(git("show", "-s", "--format=%P", "HEAD").stdout.decode().strip() == BASE,
            "Expected one direct parent at the reconciled source")
    require(git("rev-parse", BASE + "^{tree}").stdout.decode().strip() == BASE_TREE,
            "Base tree mismatch")
    changes = sorted(git("diff", "--name-only", BASE, head).stdout.decode().splitlines())
    require(changes == HELPERS, "Preparation commit changed application source")
    require(not git("status", "--porcelain").stdout, "Checkout is not clean")
    require(api("GET", "git/ref/heads/" + BRANCH)["object"]["sha"] == head,
            "Branch moved before object preparation")

    manifest_raw = Path(DATA + "/manifest.json").read_bytes()
    require(sha256(manifest_raw) == MANIFEST_SHA256, "Manifest digest mismatch")
    manifest = json.loads(manifest_raw)
    require(set(manifest) == {"base", "base_tree", "patch_sha256", "files"} and
            manifest["base"] == BASE and manifest["base_tree"] == BASE_TREE and
            sorted(manifest["files"]) == ALLOWED, "Manifest binding or population mismatch")
    patch = Path(DATA + "/verified.patch").read_bytes()
    require(0 < len(patch) <= 262144 and sha256(patch) == manifest["patch_sha256"],
            "Patch bounds or digest mismatch")
    for path, expected in manifest["files"].items():
        require(set(expected) == {"base_blob", "blob", "sha256", "bytes"}, "Invalid file metadata")
        existing = git("show", BASE + ":" + path, check=False)
        actual = blob_id(existing.stdout) if existing.returncode == 0 else None
        require(actual == expected["base_blob"], "Original file mismatch: " + path)
    git("apply", "--check", "--whitespace=error-all", DATA + "/verified.patch")
    git("apply", "--whitespace=error-all", DATA + "/verified.patch")
    git("diff", "--check")
    changed = set(git("diff", "--name-only").stdout.decode().splitlines())
    changed.update(git("ls-files", "--others", "--exclude-standard").stdout.decode().splitlines())
    require(sorted(changed) == ALLOWED, "Applied patch changed an unexpected path")
    checked = {}
    for path, expected in manifest["files"].items():
        file = Path(path)
        require(file.is_file() and not file.is_symlink(), "Unexpected file type: " + path)
        raw = file.read_bytes()
        require(len(raw) == expected["bytes"] and len(raw) <= 300000 and
                sha256(raw) == expected["sha256"] and blob_id(raw) == expected["blob"],
                "Candidate bytes mismatch: " + path)
        require(git("hash-object", path).stdout.decode().strip() == expected["blob"],
                "Independent Git blob calculation disagrees")
        checked[path] = raw
    # No repository module, native target, test, credential helper, or hook is run.
    entries = []
    for path, raw in checked.items():
        blob = api("POST", "git/blobs", {"content": base64.b64encode(raw).decode("ascii"),
                                          "encoding": "base64"})
        require(blob.get("sha") == manifest["files"][path]["blob"], "Uploaded blob mismatch")
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    # The final proposed tree removes every temporary publishing helper.
    entries.extend({"path": path, "mode": "100644", "type": "blob", "sha": None}
                   for path in HELPERS)
    input_tree = git("rev-parse", "HEAD^{tree}").stdout.decode().strip()
    tree = api("POST", "git/trees", {"base_tree": input_tree, "tree": entries})
    require(re.fullmatch(r"[0-9a-f]{40}", tree.get("sha", "")) is not None, "Invalid prepared tree")
    require(api("GET", "git/ref/heads/" + BRANCH)["object"]["sha"] == head,
            "Branch moved during object preparation; do not publish")
    return {"schema": "nico.pr1644-prepared-objects.v1", "base_commit": BASE,
            "input_commit": head, "prepared_tree": tree["sha"],
            "manifest_sha256": MANIFEST_SHA256, "patch_sha256": manifest["patch_sha256"],
            "files": manifest["files"], "temporary_helpers_removed": HELPERS,
            "ref_updated": False, "commit_created": False, "assessed_source_executed": False}


if __name__ == "__main__":
    result = prepare()
    output = Path(os.environ["RUNNER_TEMP"]) / "pr1644-prepared-objects"
    output.mkdir(exist_ok=True)
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"prepared_tree": result["prepared_tree"], "ref_updated": False}))
