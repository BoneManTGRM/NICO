from __future__ import annotations

import argparse
import json

from nico import cli_entrypoint


def test_policy_command_uses_extracted_local_store(monkeypatch, capsys):
    observed = {}

    class FakeLocalStore:
        def __init__(self, path):
            observed["path"] = path

        def policy(self):
            return {"kill_switch": True, "source": "local-store"}

    monkeypatch.setattr(cli_entrypoint, "LocalStore", FakeLocalStore)

    cli_entrypoint.dispatch(argparse.Namespace(cmd="policy"), argparse.ArgumentParser())

    assert observed["path"] == cli_entrypoint.DB_PATH
    assert json.loads(capsys.readouterr().out) == {
        "kill_switch": True,
        "source": "local-store",
    }


def test_canonical_entrypoint_does_not_expose_legacy_store():
    assert not hasattr(cli_entrypoint, "Store")
