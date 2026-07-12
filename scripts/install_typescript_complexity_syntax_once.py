from __future__ import annotations

from pathlib import Path


production = Path("nico/api/production.py")
text = production.read_text(encoding="utf-8")
text = text.replace(
    "from nico.typescript_validation_bridge import install_typescript_validation_bridge\n",
    "from nico.typescript_complexity_syntax import install_typescript_complexity_syntax\nfrom nico.typescript_validation_bridge import install_typescript_validation_bridge\n",
    1,
)
text = text.replace(
    "ASSESSMENT_SCORE_INTEGRITY = install_assessment_score_integrity()\n",
    "ASSESSMENT_SCORE_INTEGRITY = install_assessment_score_integrity()\nASSESSMENT_TYPESCRIPT_COMPLEXITY_SYNTAX = install_typescript_complexity_syntax()\n",
    1,
)
text = text.replace(
    '    "ASSESSMENT_SCORE_INTEGRITY",\n',
    '    "ASSESSMENT_SCORE_INTEGRITY",\n    "ASSESSMENT_TYPESCRIPT_COMPLEXITY_SYNTAX",\n',
    1,
)
production.write_text(text, encoding="utf-8")

builder = Path("scripts/build_complexity_manifest.py")
text = builder.read_text(encoding="utf-8")
text = text.replace(
    "from nico.assessment_score_integrity import install_assessment_score_integrity\n",
    "from nico.assessment_score_integrity import install_assessment_score_integrity\nfrom nico.typescript_complexity_syntax import install_typescript_complexity_syntax\n",
    1,
)
text = text.replace(
    "    install_assessment_score_integrity()\n",
    "    install_assessment_score_integrity()\n    install_typescript_complexity_syntax()\n",
    1,
)
builder.write_text(text, encoding="utf-8")

Path("scripts/install_typescript_complexity_syntax_once.py").unlink(missing_ok=True)
Path(".github/workflows/install-typescript-complexity-syntax.yml").unlink(missing_ok=True)
