from pathlib import Path


def test_verification_requires_post_merge_exact_commit_assessment() -> None:
    text = Path("docs/real-90-verification-v4.md").read_text(encoding="utf-8")
    assert "post-merge Comprehensive assessment" in text
    assert "exact merged commit" in text
