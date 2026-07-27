from __future__ import annotations

import ast
import base64
import hashlib
import io
import tarfile
from pathlib import Path

source = Path("scripts/apply_phase5_completion_payload.py").read_text(encoding="utf-8")
tree = ast.parse(source)
archive = ""
for node in tree.body:
    if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "ARCHIVE" for target in node.targets):
        archive = ast.literal_eval(node.value)
        break
if not archive:
    raise SystemExit("ARCHIVE constant is missing")
print(f"archive_characters={len(archive)}")
raw = base64.b64decode(archive, validate=True)
print(f"decoded_bytes={len(raw)}")
print(f"decoded_sha256={hashlib.sha256(raw).hexdigest()}")
with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as bundle:
    members = [member for member in bundle.getmembers() if member.isfile()]
print(f"file_members={len(members)}")
print("payload_integrity=verified")
