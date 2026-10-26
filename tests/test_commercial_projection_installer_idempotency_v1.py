"""Fresh-process capability reporting must support either bootstrap order."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('order', ['installer_first', 'bootstrap_first'])
def test_real_installer_and_late_bootstrap_report_consistent_capability(order):
    root = Path(__file__).resolve().parents[1]
    code = r'''
import sys
from nico import comprehensive_commercial_ship_projection_v3 as projection
from nico import comprehensive_same_run_locale_report_v1 as locale
from nico import comprehensive_manifest_navigation_v1 as navigation
assert projection._INSTALLED is False
if sys.argv[1] == 'installer_first':
    first = projection.install_comprehensive_commercial_ship_projection_v3()
else:
    from nico.api import same_run_locale_report_bootstrap as bootstrap
    first = bootstrap.COMMERCIAL_SHIP_PROJECTION
assert first['status'] == 'installed'
assert first['deployment_metric_detection_order_independent'] is True
assert first['toc_page_labels_and_bookmarks_rebuilt_after_compaction'] is True
assert projection._INSTALLED is True
target = locale._render_target
renumber = navigation._renumber_and_outline
assert getattr(target, projection._RENDER_TARGET_MARKER, False)
assert getattr(renumber, projection._NAV_MARKER, False)
second = projection.install_comprehensive_commercial_ship_projection_v3()
assert second['status'] == 'already_installed'
assert second['deployment_metric_detection_order_independent'] is True
assert second['toc_page_labels_and_bookmarks_rebuilt_after_compaction'] is True
assert second['canonical_truth_mutated'] is False
assert second['human_review_required'] is True
assert second['client_delivery_allowed'] is False
assert locale._render_target is target
assert navigation._renumber_and_outline is renumber
from nico.api import same_run_locale_report_bootstrap as bootstrap
assert bootstrap.COMMERCIAL_SHIP_PROJECTION['deployment_metric_detection_order_independent'] is True
assert bootstrap.COMMERCIAL_SHIP_PROJECTION['toc_page_labels_and_bookmarks_rebuilt_after_compaction'] is True
assert locale._render_target is target
assert navigation._renumber_and_outline is renumber
print('IDEMPOTENT_BOOTSTRAP_OK')
'''
    environment = {key: os.environ[key] for key in ('PATH', 'LANG', 'PYTHONPATH') if key in os.environ}
    environment['PYTHONPATH'] = str(root) + os.pathsep + environment.get('PYTHONPATH', '')
    completed = subprocess.run([sys.executable, '-c', code, order], cwd=root,
                               env=environment, capture_output=True, text=True,
                               timeout=45, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert 'IDEMPOTENT_BOOTSTRAP_OK' in completed.stdout
