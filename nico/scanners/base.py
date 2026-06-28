from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileContext:
    root: Path
    path: Path
    relative_path: str
    text: str
