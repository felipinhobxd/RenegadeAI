from renegade_ai.knowledge import bootstrap
from renegade_ai.knowledge import sync as sync_module


def test_ensure_renegade_dex_auto_syncs_once(monkeypatch):
    calls = {"dex": 0, "sync": 0}
    sentinel = object()

    def fake_dex():
        calls["dex"] += 1
        if calls["dex"] == 1:
            raise FileNotFoundError("missing")
        return sentinel

    def fake_sync():
        calls["sync"] += 1
        return {
            "national_dex_species": 493,
            "pokemon_records": 500,
            "moves": 400,
        }

    monkeypatch.setattr(bootstrap, "RenegadeDex", fake_dex)
    monkeypatch.setattr(sync_module, "sync_knowledge", fake_sync)

    messages = []
    result = bootstrap.ensure_renegade_dex(reporter=messages.append)

    assert result is sentinel
    assert calls == {"dex": 2, "sync": 1}
    assert any("syncing" in message.lower() for message in messages)


def test_ensure_renegade_dex_can_keep_strict_behavior(monkeypatch):
    def missing():
        raise FileNotFoundError("missing")

    monkeypatch.setattr(bootstrap, "RenegadeDex", missing)

    try:
        bootstrap.ensure_renegade_dex(auto_sync=False, reporter=None)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("strict mode should propagate missing knowledge")
