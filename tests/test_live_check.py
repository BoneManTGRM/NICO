from nico.live_score_check import live_score_check


def test_live_check_passes():
    result = live_score_check()
    assert result["status"] == "ok"
    assert result["overall_score"] > 85
