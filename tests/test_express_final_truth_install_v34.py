from nico.express_final_truth_repair_v34 import VERSION, install_express_final_truth_repair_v34


def test_final_truth_installer_preserves_review_boundary() -> None:
    status = install_express_final_truth_repair_v34()

    assert status["status"] == "installed"
    assert status["version"] == VERSION
    assert status["final_score_order_repaired"] is True
    assert status["double_deduction_removed"] is True
    assert status["terminal_progress_reconciled"] is True
    assert status["human_review_required"] is True
    assert status["client_delivery_allowed"] is False
