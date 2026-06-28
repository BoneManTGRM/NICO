from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from nico.cli import new_id, now


@dataclass
class NormalizedFinding:
    source: str
    category: str
    severity: str
    confidence: float
    affected_file: str
    business_impact: str
    technical_impact: str
    recommended_fix: str
    verification_method: str
    title: str = ''
    affected_line: int | None = None
    masked_evidence: str = ''
    raw_evidence_fingerprint: str = ''
    standards_mapping: list[str] = field(default_factory=list)
    status: str = 'open'
    finding_id: str = ''
    created_at: str = ''

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data['finding_id'] = data['finding_id'] or new_id('finding')
        data['id'] = data['finding_id']
        data['created_at'] = data['created_at'] or now()
        return data
