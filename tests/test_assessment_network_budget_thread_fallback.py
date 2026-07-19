from __future__ import annotations

from nico import assessment_network_budget as budget


def test_parallel_fetch_falls_back_to_serial_when_thread_pool_cannot_start(monkeypatch):
    class BrokenExecutor:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("can't start new thread")

    monkeypatch.setattr(budget, "ThreadPoolExecutor", BrokenExecutor)

    calls: list[str] = []

    def fetcher(path: str):
        calls.append(path)
        return f"content:{path}", None

    result = budget._parallel_fetch(["a.py", "b.py", "a.py"], fetcher)

    assert calls == ["a.py", "b.py"]
    assert result == {
        "a.py": ("content:a.py", None),
        "b.py": ("content:b.py", None),
    }


def test_parallel_fetch_serial_fallback_contains_per_file_failure(monkeypatch):
    class BrokenExecutor:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("can't start new thread")

    monkeypatch.setattr(budget, "ThreadPoolExecutor", BrokenExecutor)

    def fetcher(path: str):
        if path == "bad.py":
            raise ValueError("unavailable")
        return "ok", None

    result = budget._parallel_fetch(["good.py", "bad.py"], fetcher)

    assert result["good.py"] == ("ok", None)
    assert result["bad.py"][0] is None
    assert "bounded collection window" in str(result["bad.py"][1])
