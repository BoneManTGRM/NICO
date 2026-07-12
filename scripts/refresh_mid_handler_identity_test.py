from __future__ import annotations

from pathlib import Path


path = Path("tests/test_mid_assessment_api.py")
text = path.read_text(encoding="utf-8")
text = text.replace(
    "from nico.snapshot_assessment_handlers import (\n    _snapshot_evidence_attachment_handler,\n    _snapshot_scanner_handler,\n)\n",
    "import nico.snapshot_assessment_handlers as snapshot_handlers\n",
)
text = text.replace(
    'assert configured["scanner_worker"] is _snapshot_scanner_handler\n    assert configured["evidence_attachment"] is _snapshot_evidence_attachment_handler',
    'assert configured["scanner_worker"] is snapshot_handlers._snapshot_scanner_handler\n    assert configured["evidence_attachment"] is snapshot_handlers._snapshot_evidence_attachment_handler',
)
text = text.replace(
    'assert handlers["scanner_worker"] is _snapshot_scanner_handler',
    'assert handlers["scanner_worker"] is snapshot_handlers._snapshot_scanner_handler',
)
path.write_text(text, encoding="utf-8")
Path("scripts/refresh_mid_handler_identity_test.py").unlink(missing_ok=True)
Path(".github/workflows/refresh-mid-handler-identity-test.yml").unlink(missing_ok=True)
