from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]
