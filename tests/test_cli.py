from nico.cli import Store, generate_reports, mask_text, scan_drift_demo, scan_test_lab, scanner_availability, verify_latest


def test_scan_test_lab():
    result = scan_test_lab()
    assert result['scan']['findings']
    assert result['repairs']
    assert 'rye' in result['scan']['findings'][0]


def test_drift_demo():
    assert scan_drift_demo()['drift']


def test_secret_masking():
    assert 'FAKE_TEST_ONLY_SECRET_123456' not in mask_text('API_KEY="FAKE_TEST_ONLY_SECRET_123456"')


def test_verify_and_report():
    assert verify_latest()['passed'] is True
    assert generate_reports()


def test_policy_blocks():
    assert 'exploit' in Store().policy()['blocked_actions']


def test_scanner_availability_shape():
    tools = scanner_availability()
    assert tools
    assert {'tool', 'purpose', 'available', 'mode'} <= set(tools[0])
