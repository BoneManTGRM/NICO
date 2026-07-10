from nico.modules.github_url_safety import is_github_repo_url, parse_github_repo


def test_parse_github_repo_accepts_canonical_url() -> None:
    assert parse_github_repo("https://github.com/BoneManTGRM/NICO") == ("BoneManTGRM", "NICO")
    assert parse_github_repo("github.com/BoneManTGRM/NICO.git") == ("BoneManTGRM", "NICO")


def test_parse_github_repo_rejects_substring_host_bypass() -> None:
    assert parse_github_repo("https://github.com.evil.test/BoneManTGRM/NICO") == (None, None)
    assert parse_github_repo("https://evil.test/github.com/BoneManTGRM/NICO") == (None, None)
    assert is_github_repo_url("https://github.com.evil.test/BoneManTGRM/NICO") is False


def test_parse_github_repo_rejects_invalid_repo_parts() -> None:
    assert parse_github_repo("https://github.com/BoneManTGRM/NICO?x=1") == ("BoneManTGRM", "NICO")
    assert parse_github_repo("https://github.com/BoneManTGRM/no spaces") == (None, None)
