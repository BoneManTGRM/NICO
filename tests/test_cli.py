from nico.cli import scan_test_lab, scan_drift_demo, verify_latest, generate_reports, Store, mask_text

def test_scan_test_lab():
    assert scan_test_lab()['scan']['findings']

def test_drift_demo():
    assert scan_drift_demo()['drift']

def test_secret_masking():
    assert 'FAKE_TEST_ONLY_SECRET_123456' not in mask_text('API_KEY="FAKE_TEST_ONLY_SECRET_123456"')

def test_verify_and_report():
    assert verify_latest()['passed'] is True
    assert generate_reports()

def test_policy_blocks():
    assert 'exploit' in Store().policy()['blocked_actions']
