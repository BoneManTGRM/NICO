from __future__ import annotations

import threading
import time

from nico.express_atomic_start_lock import _scope_lock_id, atomic_express_start_lock


class _MemoryStore:
    class Adapter:
        pass

    adapter = Adapter()

    def status(self) -> dict:
        return {"adapter": "memory", "mode": "memory"}


def test_scope_lock_id_is_stable_and_scope_specific() -> None:
    a = ("BoneManTGRM/NICO", "customer", "project")
    b = ("BoneManTGRM/NICO", "customer", "other")
    assert _scope_lock_id(a) == _scope_lock_id(a)
    assert _scope_lock_id(a) != _scope_lock_id(b)
    assert -(1 << 63) <= _scope_lock_id(a) < (1 << 63)


def test_memory_scope_lock_serializes_check_and_start_boundary() -> None:
    store = _MemoryStore()
    scope = ("BoneManTGRM/NICO", "customer", "project")
    order: list[str] = []
    first_entered = threading.Event()
    release_first = threading.Event()

    def first() -> None:
        with atomic_express_start_lock(store, scope):
            order.append("first-enter")
            first_entered.set()
            release_first.wait(2)
            order.append("first-exit")

    def second() -> None:
        first_entered.wait(2)
        with atomic_express_start_lock(store, scope):
            order.append("second-enter")

    one = threading.Thread(target=first)
    two = threading.Thread(target=second)
    one.start()
    two.start()
    assert first_entered.wait(2)
    time.sleep(0.05)
    assert order == ["first-enter"]
    release_first.set()
    one.join(2)
    two.join(2)
    assert order == ["first-enter", "first-exit", "second-enter"]


def test_different_scopes_do_not_block_each_other() -> None:
    store = _MemoryStore()
    entered = threading.Event()
    release = threading.Event()

    def hold_first() -> None:
        with atomic_express_start_lock(store, ("repo", "customer", "one")):
            entered.set()
            release.wait(2)

    thread = threading.Thread(target=hold_first)
    thread.start()
    assert entered.wait(2)
    with atomic_express_start_lock(store, ("repo", "customer", "two")) as evidence:
        assert evidence["mode"] == "process_local_memory_lock"
    release.set()
    thread.join(2)
