from nico.express_final_gate_checkpoint_patch import _terminal_report_projection


class _Api:
    @staticmethod
    def _stage_progress(active_step, active_status, message, *, evidence=None):
        stages = [
            "request_accepted",
            "repository_evidence",
            "scanner_reconciliation",
            "accuracy_review",
            "score_reconciliation",
            "report_generation",
            "truth_and_review_gates",
            "complete",
        ]
        active_index = stages.index(active_step)
        return [
            {
                "step": step,
                "status": active_status if step == active_step else "complete" if index < active_index else "pending",
                "message": message if step == active_step else step,
                "evidence": dict(evidence or {}) if step == active_step else {},
            }
            for index, step in enumerate(stages)
        ]


def test_downloadable_report_never_leaves_truth_gate_running():
    result = {
        "current_stage": "report_generation",
        "progress_percent": 82,
        "progress": [{"step": "truth_and_review_gates", "status": "running"}],
        "human_review_required": True,
        "client_ready": False,
    }
    projected = _terminal_report_projection(_Api, result)
    truth = next(item for item in projected["progress"] if item["step"] == "truth_and_review_gates")
    assert truth["status"] == "complete"
    assert projected["current_stage"] == "complete"
    assert projected["progress_percent"] == 100
    assert projected["human_review_required"] is True
    assert projected["client_delivery_allowed"] is False


def test_terminal_report_projection_does_not_mutate_live_runtime_state():
    result = {
        "current_stage": "truth_and_review_gates",
        "progress_percent": 94,
        "progress": [{"step": "truth_and_review_gates", "status": "running"}],
    }
    _terminal_report_projection(_Api, result)
    assert result["current_stage"] == "truth_and_review_gates"
    assert result["progress_percent"] == 94
    assert result["progress"][0]["status"] == "running"
