from pathlib import Path


def test_provider_collection_documentation_exists_in_both_locales() -> None:
    root = Path(__file__).resolve().parents[1]
    english = root / "docs" / "provider_collection_runtime.md"
    spanish = root / "docs" / "provider_collection_runtime_es.md"
    assert english.exists()
    assert spanish.exists()
    assert english.read_text(encoding="utf-8").strip()
    assert spanish.read_text(encoding="utf-8").strip()


def test_provider_collection_documentation_has_matching_structure() -> None:
    root = Path(__file__).resolve().parents[1]
    texts = [
        (root / "docs" / "provider_collection_runtime.md").read_text(encoding="utf-8"),
        (root / "docs" / "provider_collection_runtime_es.md").read_text(encoding="utf-8"),
    ]
    headings = [[line for line in text.splitlines() if line.startswith("#")] for text in texts]
    paragraphs = [[part for part in text.split("\n\n") if part.strip()] for text in texts]
    assert len(headings[0]) == len(headings[1]) == 1
    assert len(paragraphs[0]) == len(paragraphs[1])
