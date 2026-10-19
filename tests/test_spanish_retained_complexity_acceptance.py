"""Direct canonical localization must not depend on worker installer order."""
import json
import subprocess
import sys

import pytest

CRITERION = (
    "The exact-SHA rerun no longer reports cyclomatic complexity of 30 or greater "
    "at nico/assessment_cpp_configuration_probe.py:64"
)


def localize(value):
    # Fresh interpreter prevents global installer state from masking the defect.
    code = '''
import json, sys, types
from pathlib import Path
# Load source without the package's optional global installer side effects.
package = types.ModuleType("nico")
package.__path__ = [str(Path.cwd() / "nico")]
sys.modules["nico"] = package
from nico.comprehensive_spanish_canonical_report_v87 import _localize_tree
value = json.loads(sys.argv[1])
print(json.dumps(_localize_tree(value), ensure_ascii=False))
'''
    return subprocess.run([sys.executable, "-c", code, json.dumps(value)],
                          capture_output=True, text=True)


@pytest.mark.parametrize("period", ["", "."])
@pytest.mark.parametrize("field", ["acceptance_criteria", "verification"])
def test_retained_inclusive_criterion_without_installers(field, period):
    source = {"finding_id": "NICO-FINDING-123", field: [CRITERION + period]}
    result = localize(source)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "finding_id": "NICO-FINDING-123", field: [
            "La nueva ejecución sobre el SHA exacto ya no informa una complejidad "
            "ciclomática igual o superior a 30 en nico/assessment_cpp_configuration_probe.py:64."
        ]}


@pytest.mark.parametrize("value", [
    CRITERION + " unless checks fail",
    CRITERION.replace("or greater", "or smaller"),
    CRITERION.replace("exact-SHA", "approximate-SHA"),
    CRITERION.replace(":64", ":unknown"),
    "Future untranslated acceptance criterion requires review and remains blocked before client delivery",
])
def test_unknown_criterion_still_fails_closed(value):
    result = localize({"acceptance_criteria": [value]})
    assert result.returncode != 0
    assert "missing Spanish presentation translation" in result.stderr
