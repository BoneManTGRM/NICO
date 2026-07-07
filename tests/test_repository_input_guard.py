from nico.repository_input_guard import repository_suggestion, sanitize_repository_error


def test_repository_suggestion_catches_typo():
    assert repository_suggestion("BoneManTGRM/NOCO") == "BoneManTGRM/NICO"


def test_sanitize_repository_error_returns_safe_message():
    result = sanitize_repository_error("BoneManTGRM/NOCO", "404")

    assert result["status"] == "not_found"
    assert result["suggested_repository"] == "BoneManTGRM/NICO"
