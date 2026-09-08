"""Bounded static source observations, not inferred or verified runtime topology."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any, Mapping

VERSION = "nico.source_architecture_observation.v1"
_SHA = re.compile(r"^[0-9a-f]{40}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")


def _digest(value: Mapping[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "observation_sha256"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""



def _masked_javascript(source: str) -> str:
    # Keep offsets and line numbers while excluding comments and literal text.
    # Template expressions are deliberately unobserved by this bounded lexer.
    pattern = re.compile(
        r"/\*.*?\*/|//[^\n]*|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|\x60(?:\\.|[^\x60\\])*\x60|/(?![/*])(?:\\.|[^/\\\n])+/[dgimsuvy]*",
        re.DOTALL,
    )
    return pattern.sub(lambda match: "".join("\n" if char == "\n" else " " for char in match.group()), source)


def _javascript_call_site(cleaned: str, start: int, opening: int) -> bool:
    """Reject member names and method/type declarations before call credit."""
    if start and (cleaned[start - 1].isalnum() or cleaned[start - 1] in "_.$"):
        return False
    depth = 1
    closing = opening + 1
    while closing < len(cleaned) and depth:
        depth += (cleaned[closing] == "(") - (cleaned[closing] == ")")
        closing += 1
    after = cleaned[closing:].lstrip()
    return depth == 0 and not after.startswith(("{", ":", "=>"))


def analyze_source_architecture(
    files: Mapping[str, str], *, run_id: str, repository: str,
    commit_sha: str, snapshot_id: str,
) -> dict[str, Any]:
    if not run_id or not repository or not snapshot_id or not _SHA.fullmatch(commit_sha):
        raise ValueError("source_architecture_identity_required")
    inventory = []
    components = []
    interactions = []
    infrastructure = []
    dependencies = []
    parser_notes = []

    for path, source in sorted(files.items()):
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        inventory.append({"path": path, "observed_text_sha256": digest,
                          "observed_text_bytes": len(source.encode("utf-8")),
                          "observed_line_count": len(source.splitlines())})
        evidence = {"path": path, "observed_text_sha256": digest, "commit_sha": commit_sha}
        name = PurePosixPath(path).name

        def edge(kind: str, target: str, line: int, boundary: str = "") -> None:
            interactions.append({"source": path, "target": target, "kind": kind,
                                 "potential_boundary": boundary,
                                 "runtime_verified": False,
                                 "evidence": {**evidence, "line": line}})

        if path.lower().endswith(".py"):
            try:
                tree = ast.parse(source)
            except (SyntaxError, ValueError):
                parser_notes.append(f"{path}: Python syntax could not be parsed; no architecture observations credited.")
                continue
            components.append({"id": path, "path": path, "kind": "source_module",
                               "language": "python", "evidence": evidence})
            aliases: dict[str, str] = {}
            shadowed = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del))}
            shadowed.update(node.arg for node in ast.walk(tree) if isinstance(node, ast.arg))
            shadowed.update(node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if node in tree.body:
                            aliases[alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]
                        edge("import", alias.name, node.lineno)
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        target = "." * node.level + (node.module or "")
                        if node in tree.body:
                            aliases[alias.asname or alias.name] = f"{target}.{alias.name}"
                        edge("import", target or ".", node.lineno)
            decorators = {id(deco) for owner in ast.walk(tree)
                          if isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef))
                          for deco in owner.decorator_list}
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                call = _call_name(node.func)
                first, _, rest = call.partition(".")
                if first in shadowed:
                    continue
                qualified = aliases.get(first, first) + ("." + rest if rest else "")
                if first not in aliases and first != "open":
                    continue
                if re.fullmatch(r"(requests|httpx)\.(get|post|put|patch|delete|request|head|options)", qualified) or qualified in {"urllib.request.urlopen", "urllib.request.urlretrieve"}:
                    edge("http_call", qualified, node.lineno, "outbound_network_destination_unresolved")
                elif qualified in {"sqlite3.connect", "psycopg.connect", "psycopg2.connect", "sqlalchemy.create_engine", "pymongo.MongoClient", "redis.Redis", "open", "builtins.open"}:
                    edge("storage_call", qualified, node.lineno, "storage_target_and_access_policy_unresolved")
                elif qualified in {"subprocess.run", "subprocess.Popen", "subprocess.call", "subprocess.check_call", "subprocess.check_output", "os.system", "os.execv"}:
                    edge("process_call", qualified, node.lineno, "child_process_privilege_boundary_unresolved")
                elif re.fullmatch(r"\w+\.(get|post|put|patch|delete|route|websocket)", call):
                    # Only a decorator is a route declaration; a client method
                    # with the same spelling does not become a server endpoint.
                    if id(node) in decorators:
                        edge("route_declaration", call, node.lineno, "incoming_request_authorization_unverified")
        elif path.lower().endswith((".js", ".jsx", ".ts", ".tsx")):
            components.append({"id": path, "path": path, "kind": "source_module",
                               "language": "javascript-typescript", "evidence": evidence})
            cleaned = _masked_javascript(source)
            for match in re.finditer(r"\b(fetch|axios\.(?:get|post|put|patch|delete|request)|fs\.(?:readFile|writeFile|readFileSync|writeFileSync)|child_process\.(?:exec|execFile|spawn))\s*\(", cleaned):
                call = match.group(1)
                if not _javascript_call_site(cleaned, match.start(), match.end() - 1):
                    continue
                root = call.split(".")[0]
                # Locally declared or parameter-bound names are unresolved by
                # this bounded lexer. Prefer omission to an invented network edge.
                if re.search(r"\b(?:const|let|var|function|class|import)\s+[^;\n]*\b" + re.escape(root) + r"\b", cleaned) or re.search(r"(?:\(|,)\s*" + re.escape(root) + r"\s*(?:[:,)=])", cleaned):
                    continue
                if root != "fetch":
                    continue
                kind = "storage_call" if call.startswith("fs.") else "process_call" if call.startswith("child_process.") else "http_call"
                edge(kind, call, cleaned.count("\n", 0, match.start()) + 1,
                     {"http_call": "outbound_network_destination_unresolved",
                      "storage_call": "storage_target_and_access_policy_unresolved",
                      "process_call": "child_process_privilege_boundary_unresolved"}[kind])
            for match in re.finditer(r"\b(?:import|export)\s+(?:[^;\n]*?\bfrom\s*)?[\"']([^\"'\n]+)[\"']", source):
                if cleaned[match.start():].startswith(("import", "export")):
                    edge("import", match.group(1), source.count("\n", 0, match.start()) + 1)
        elif name == "Dockerfile":
            declarations = []
            for line_no, line in enumerate(source.splitlines(), 1):
                instruction = line.strip().split(None, 1)[0].upper() if line.strip() else ""
                if instruction in {"FROM", "USER", "EXPOSE", "ENTRYPOINT", "CMD", "HEALTHCHECK", "VOLUME"}:
                    # Retain instruction types and source locations, not command
                    # values that can contain private endpoints or credentials.
                    declarations.append({"instruction": instruction, "line": line_no})
            infrastructure.append({"path": path, "kind": "declared_container_configuration",
                                   "declarations": declarations, "runtime_verified": False,
                                   "evidence": evidence})
        elif name in {"vercel.json", "railway.json", "package.json"}:
            try:
                manifest = json.loads(source)
                if not isinstance(manifest, dict):
                    raise ValueError("manifest_object_required")
            except (ValueError, TypeError):
                parser_notes.append(f"{path}: JSON manifest could not be parsed.")
                continue
            if name == "package.json":
                names = sorted({str(key) for field in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
                                if isinstance(manifest.get(field), dict) for key in manifest[field]})
                dependencies.append({"path": path, "ecosystem": "npm", "names": names,
                                     "installation_verified": False, "evidence": evidence})
            else:
                infrastructure.append({"path": path, "kind": "declared_provider_configuration",
                                       "provider": "vercel" if name == "vercel.json" else "railway",
                                       "declared_keys": sorted(manifest), "runtime_verified": False,
                                       "evidence": evidence})
        elif name in {"Procfile", "railway.toml", "fly.toml", "render.yaml"}:
            infrastructure.append({"path": path, "kind": "declared_deployment_manifest",
                                   "runtime_verified": False, "evidence": evidence})

    observation = {
        "version": VERSION, "run_id": run_id, "repository": repository,
        "commit_sha": commit_sha, "snapshot_id": snapshot_id,
        "collection_scope": "observed_source_text_sample",
        "runtime_topology_verified": False,
        "input_inventory": inventory, "components": components,
        "interactions": sorted(interactions, key=lambda item: (item["source"], item["evidence"]["line"], item["kind"], item["target"])),
        "declared_infrastructure": infrastructure,
        "dependency_declarations": dependencies,
        "parser_notes": parser_notes,
        "unknowns": [
            "Source observations do not verify deployed services, active network routes, storage contents, or runtime authorization.",
            "Potential trust boundaries identify static call sites for review; endpoints, privileges, and protections remain unverified.",
            "JavaScript/TypeScript observations use bounded lexical matching; dynamic imports, aliases, and computed calls can be absent.",
            "Shadowed or locally bound call names are conservatively omitted; source observations do not resolve every language scope or method dispatch.",
            "The sampled source text is hashed after decoding; these hashes do not assert retention of original repository file bytes.",
        ],
    }
    observation["observation_sha256"] = _digest(observation)
    return observation


def verified_observation(repository_evidence: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any] | None:
    """Consume only a self-consistent observation from this run's exact snapshot."""
    architecture = repository_evidence.get("architecture_evidence")
    if not isinstance(architecture, Mapping):
        return None
    observation = architecture.get("source_observation")
    if not isinstance(observation, Mapping) or observation.get("version") != VERSION:
        return None
    stages = context.get("prior_stage_results")
    if not isinstance(stages, Mapping):
        return None
    snapshot_stage = stages.get("immutable_repository_snapshot")
    if not isinstance(snapshot_stage, Mapping):
        return None
    snapshot = snapshot_stage.get("snapshot")
    if not isinstance(snapshot, Mapping):
        return None
    expected = {"run_id": context.get("run_id"), "repository": context.get("repository"),
                "commit_sha": context.get("commit_sha"), "snapshot_id": snapshot.get("snapshot_id")}
    if any(not value or observation.get(key) != value for key, value in expected.items()):
        return None
    if not _SHA.fullmatch(str(expected["commit_sha"])):
        return None
    if any(repository_evidence.get(key) != expected[key] for key in ("run_id", "repository", "snapshot_id")):
        return None
    if repository_evidence.get("snapshot_commit_sha") != expected["commit_sha"]:
        return None
    if snapshot.get("commit_sha") != expected["commit_sha"] or snapshot.get("run_id") != expected["run_id"] or snapshot.get("repository") != expected["repository"]:
        return None
    if observation.get("runtime_topology_verified") is not False or observation.get("collection_scope") != "observed_source_text_sample":
        return None
    try:
        if observation.get("observation_sha256") != _digest(observation):
            return None
        inventory = {}
        for item in observation["input_inventory"]:
            if not isinstance(item, Mapping):
                return None
            path, digest = item["path"], item["observed_text_sha256"]
            lines = item.get("observed_line_count")
            if not isinstance(path, str) or not path or path in inventory or not isinstance(digest, str) or not _HASH.fullmatch(digest):
                return None
            if type(lines) is not int or lines < 0 or type(item.get("observed_text_bytes")) is not int or item["observed_text_bytes"] < 0:
                return None
            inventory[path] = item
        for field in ("unknowns", "parser_notes"):
            if not isinstance(observation[field], list) or any(not isinstance(value, str) for value in observation[field]):
                return None
        for field in ("components", "interactions", "declared_infrastructure", "dependency_declarations"):
            if not isinstance(observation[field], list):
                return None
            for item in observation[field]:
                if not isinstance(item, Mapping) or not isinstance(item.get("evidence"), Mapping):
                    return None
                evidence = item["evidence"]
                retained = inventory.get(evidence.get("path"))
                if retained is None or evidence.get("commit_sha") != expected["commit_sha"] or retained["observed_text_sha256"] != evidence.get("observed_text_sha256"):
                    return None
                if item.get("runtime_verified", False) is not False:
                    return None
                alias = "source" if field == "interactions" else "path"
                if item.get(alias) != evidence["path"]:
                    return None
                if field == "components":
                    if item.get("id") != evidence["path"] or item.get("kind") != "source_module" or item.get("language") not in {"python", "javascript-typescript"}:
                        return None
                elif field == "interactions":
                    if item.get("kind") not in {"import", "http_call", "storage_call", "process_call", "route_declaration"}:
                        return None
                    if not isinstance(item.get("target"), str) or not isinstance(item.get("potential_boundary"), str):
                        return None
                    line = evidence.get("line")
                    if type(line) is not int or not 1 <= line <= retained["observed_line_count"]:
                        return None
                elif field == "declared_infrastructure":
                    if item.get("kind") not in {"declared_container_configuration", "declared_provider_configuration", "declared_deployment_manifest"}:
                        return None
                elif not isinstance(item.get("names"), list) or any(not isinstance(name, str) for name in item["names"]):
                    return None
    except (KeyError, TypeError, ValueError):
        return None
    return copy.deepcopy(dict(observation))


def structured_tables(observation: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Renderer-neutral facts; complete observation remains alongside these tables."""
    return [
        {"title": "Observed source components", "columns": ["Source", "Kind", "Language"],
         "rows": [[row["path"], row["kind"], row["language"]] for row in observation["components"]]},
        {"title": "Source interactions and potential boundaries", "columns": ["Source", "Operation", "Target", "Potential boundary", "Line"],
         "rows": [[row["source"], row["kind"], row["target"], row["potential_boundary"], row["evidence"]["line"]] for row in observation["interactions"]]},
        {"title": "Declared infrastructure", "columns": ["Source", "Declaration", "Runtime verified"],
         "rows": [[row["path"], row["kind"], False] for row in observation["declared_infrastructure"]]},
    ]
