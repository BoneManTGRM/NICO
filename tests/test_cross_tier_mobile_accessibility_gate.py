from copy import deepcopy

from nico.cross_tier_mobile_accessibility_gate import evaluate_cross_tier_mobile_accessibility


def _tier(name: str) -> dict:
    return {
        "tier": name,
        "viewports": [320, 375, 390, 414],
        "checks": {
            "no_horizontal_overflow": True,
            "no_clipped_text": True,
            "no_overlapping_controls": True,
            "primary_actions_visible": True,
            "keyboard_navigation": True,
            "visible_focus": True,
            "semantic_headings": True,
            "form_labels": True,
            "screen_reader_summary": True,
            "contrast_pass": True,
            "reduced_motion": True,
            "download_flow_pass": True,
        },
        "locale_parity": True,
        "download_content_disposition": True,
        "download_content_length": True,
        "touch_target_min_px": 44,
        "client_delivery_blocked": False,
    }


def _payload() -> dict:
    return {"tiers": {name: _tier(name) for name in ("express", "mid", "full")}}


def test_all_tiers_pass_mobile_accessibility_gate():
    result = evaluate_cross_tier_mobile_accessibility(_payload())
    assert result["approved"] is True
    assert result["client_delivery_allowed"] is True
    assert result["issues"] == []


def test_missing_iphone_width_fails_closed():
    payload = _payload()
    payload["tiers"]["express"]["viewports"].remove(375)
    result = evaluate_cross_tier_mobile_accessibility(payload)
    assert result["approved"] is False
    assert "missing_viewport:express:375" in result["issues"]


def test_accessibility_failure_blocks_delivery():
    payload = _payload()
    payload["tiers"]["mid"]["checks"]["visible_focus"] = False
    result = evaluate_cross_tier_mobile_accessibility(payload)
    assert result["client_delivery_allowed"] is False
    assert "failed_check:mid:visible_focus" in result["issues"]


def test_download_and_touch_target_failures_are_reported():
    payload = _payload()
    payload["tiers"]["full"]["download_content_length"] = False
    payload["tiers"]["full"]["touch_target_min_px"] = 40
    result = evaluate_cross_tier_mobile_accessibility(payload)
    assert "missing_download_length:full" in result["issues"]
    assert "touch_target_too_small:full" in result["issues"]


def test_cross_tier_identity_and_locale_parity_are_required():
    payload = _payload()
    payload["tiers"]["express"]["tier"] = "mid"
    payload["tiers"]["mid"]["locale_parity"] = False
    result = evaluate_cross_tier_mobile_accessibility(payload)
    assert "tier_identity_mismatch:express" in result["issues"]
    assert "locale_parity_failed:mid" in result["issues"]


def test_missing_tier_and_prior_block_fail_closed():
    payload = _payload()
    del payload["tiers"]["full"]
    payload["tiers"]["express"]["client_delivery_blocked"] = True
    result = evaluate_cross_tier_mobile_accessibility(payload)
    assert "missing_tier:full" in result["issues"]
    assert "prior_delivery_block:express" in result["issues"]
