from pathlib import Path
import json
import re
import os
import subprocess
import sys
import io
import tarfile

import pytest


def _assert_node_stages(dockerfile, expected):
    # Inspect every FROM, including tags that do not match a numeric-major
    # pattern. Exact stage order also rejects missing or duplicate stages.
    stages = re.findall(r"(?im)^\s*FROM\s+([^\n]+)", dockerfile)
    assert [stage.strip() for stage in stages] == expected


def test_dockerfile_uses_deterministic_npm_install_for_railway_web_dependencies():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "cd apps/web && npm ci --ignore-scripts --no-audit --no-fund" in dockerfile
    assert "npm install --legacy-peer-deps" not in dockerfile


def test_docker_node_stages_match_web_engine_requirement():
    required = json.loads(Path("apps/web/package.json").read_text())["engines"]["node"]
    major = required.removesuffix(".x")
    assert major.isdigit(), "Update this contract for a non-major Node engine range"
    backend = Path("Dockerfile").read_text()
    web = Path("apps/web/Dockerfile").read_text()
    _assert_node_stages(backend, [
        f"node:{major}-bookworm-slim AS node-runtime",
        "python:3.11-slim",
    ])
    _assert_node_stages(web, [
        f"node:{major}-alpine AS {stage}"
        for stage in ("dependencies", "builder", "runner")
    ])

    # The backend must actually use the selected runtime for global scanner
    # tools and web dependencies, without reintroducing distro Node/npm.
    assert "COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node" in backend
    assert "COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules" in backend
    assert "../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm" in backend
    assert "../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx" in backend
    assert not re.search(r"(?m)^\s+(?:nodejs|npm)\s+\\$", backend)
    assert "        libatomic1 " in backend
    assert "        libstdc++6 " in backend
    assert backend.index("COPY --from=node-runtime") < backend.index("RUN npm install -g")


@pytest.mark.parametrize("replacement", [
    "",  # missing runner
    "FROM node:20-alpine AS runner",
    "FROM node:latest AS runner",  # previously unmatched incompatible tag
    "FROM node:lts-alpine AS runner",
    "FROM node:24-alpine AS wrong-name",
    "FROM node:24-alpine AS runner\nFROM node:20 AS extra",
    "FROM node:24-alpine AS runner\nFROM node:24-alpine AS runner",
])
def test_node_stage_contract_rejects_incomplete_or_incompatible_stages(replacement):
    expected = [f"node:24-alpine AS {name}" for name in ("dependencies", "builder", "runner")]
    dockerfile = "\n".join(f"FROM {stage}" for stage in expected[:2]) + "\n" + replacement
    with pytest.raises(AssertionError):
        _assert_node_stages(dockerfile, expected)


def test_all_node_stages_pin_declared_npm_before_use():
    manager = json.loads(Path("apps/web/package.json").read_text())["packageManager"]
    assert manager == "npm@10.8.2"
    pin = f"RUN npm install --global {manager} --ignore-scripts --no-audit --no-fund"
    for filename in ("Dockerfile", "apps/web/Dockerfile"):
        stages = re.split(r"(?m)^FROM ", Path(filename).read_text())[1:]
        for stage in stages:
            if stage.startswith("node:"):
                assert stage.splitlines()[1] == pin


@pytest.mark.parametrize("fail_exec,expected_containers", [(False, 3), (True, 1)])
def test_smoke_script_cleans_only_created_containers(tmp_path, fail_exec, expected_containers):
    # Execute the real shell control flow with a fake Docker CLI: no builds,
    # network, containers, package installation, or production interaction.
    log = tmp_path / "docker.jsonl"
    counter = tmp_path / "count"
    docker = tmp_path / "docker"
    docker.write_text(f"#!{sys.executable}\n" + '''
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['DOCKER_TEST_LOG'], 'a') as out:
    out.write(json.dumps(args) + '\\n')
if args[0] == 'create':
    counter = pathlib.Path(os.environ['DOCKER_TEST_COUNTER'])
    count = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(count))
    print('created-' + str(count))
if args[0] == 'exec':
    sys.stdin.read()
    if os.environ['DOCKER_TEST_FAIL'] == '1':
        sys.exit(7)
''')
    docker.chmod(0o755)
    env = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}",
               DOCKER_TEST_LOG=str(log), DOCKER_TEST_COUNTER=str(counter),
               DOCKER_TEST_FAIL=str(int(fail_exec)))
    result = subprocess.run(["bash", "scripts/qualify_docker_node_runtime.sh"],
                            env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == (7 if fail_exec else 0), result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    creates = [call for call in calls if call[0] == "create"]
    assert len(creates) == expected_containers
    assert all("--network=none" in call for call in creates)
    assert [call for call in calls if call[0] == "rm"] == [
        ["rm", "-f", f"created-{index}"] for index in range(1, expected_containers + 1)
    ]


def test_ci_qualifies_both_local_images_with_bounded_budget():
    workflow = Path(".github/workflows/nico-ci.yml").read_text()
    block = workflow.split("- name: Run Docker build check", 1)[1].split("- name:", 1)[0]
    assert "timeout-minutes: 20" in block
    assert "timeout --kill-after=10s 720s docker build" in block
    assert 'timeout --kill-after=10s 360s docker build -t nico-web-ci:ci "$docker_context/apps/web"' in block
    assert "timeout --kill-after=10s 90s bash scripts/qualify_docker_node_runtime.sh" in block
    script = Path("scripts/qualify_docker_node_runtime.sh").read_text()
    for marker in ("{{.Architecture}}", "id -un", "npm --version", "npx --version",
                   'ldd "$(command -v node)"', "Error relocating", "eslint --no-config-lookup",
                   "tsc --noEmit", "http://127.0.0.1:3000/api/deployment"):
        assert marker in script


def test_web_context_excludes_host_outputs_and_private_configuration():
    rules = Path("apps/web/.dockerignore").read_text().splitlines()
    for pattern in ("node_modules", "**/node_modules", ".next", "**/.next",
                    ".env", ".env.*", "**/.env", "**/.env.*", ".npmrc", "**/.npmrc",
                    "*.pem", "*.key", "**/*.pem", "**/*.key"):
        assert pattern in rules
    # Only the deliberately retained nonsecret template is re-included.
    assert [rule for rule in rules if rule.startswith("!")] == ["!.env.example"]
    assert rules.index("!.env.example") > rules.index("**/.env.*")
    assert Path("apps/web/.env.example").is_file()


def test_docker_qualification_archives_committed_package_inputs():
    workflow = Path(".github/workflows/nico-ci.yml").read_text()
    block = workflow.split("- name: Run Docker build check", 1)[1].split("- name: ", 1)[0]
    assert 'docker_context=$(mktemp -d)' in block
    assert 'git archive HEAD | tar --extract -C "$docker_context"' in block
    assert 'trap \'rm -rf -- "$docker_context"\' EXIT' in block
    assert '-t nico-ci:ci "$docker_context"' in block
    assert '-t nico-web-ci:ci "$docker_context/apps/web"' in block
    assert block.index("git archive HEAD") < block.index("docker build")
    assert "git reset" not in block and "git clean" not in block and "git checkout" not in block
    # Read the actual archive, without modifying the checkout or creating a
    # commit. These bytes come from HEAD regardless of working-tree edits.
    archive = subprocess.check_output(["git", "archive", "HEAD", "apps/web"])
    with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
        for filename in ("apps/web/package.json", "apps/web/package-lock.json"):
            assert tree.extractfile(filename).read() == subprocess.check_output(
                ["git", "show", f"HEAD:{filename}"])
        assert not any(name.startswith(("apps/web/node_modules/", "apps/web/.next/"))
                       for name in tree.getnames())
