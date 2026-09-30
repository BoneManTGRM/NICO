from scripts.comprehensive_recovery_observation_v1 import recovery_boundary_observed


def test_old_terminal_acknowledgement_and_active_revision_are_not_results():
    assert not recovery_boundary_observed({"revision": 40, "terminal": True}, initial_revision=40)
    assert not recovery_boundary_observed({"revision": 41, "terminal": False}, initial_revision=40)
    assert recovery_boundary_observed({"revision": 42, "terminal": True}, initial_revision=40)


def test_missing_or_invalid_revision_cannot_certify_recovery():
    for revision in (None, True, "42", 39):
        assert not recovery_boundary_observed({"revision": revision, "terminal": True}, initial_revision=40)
