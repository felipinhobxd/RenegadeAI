from renegade_ai.state.runtime import RuntimeMove, RuntimeStateStore


def test_runtime_state_round_trip(tmp_path):
    path = tmp_path / "state.json"
    store = RuntimeStateStore(path)
    profile = store.upsert(
        "chimchar",
        "Chimchar",
        level=5,
        hp_current=14,
        hp_max=20,
        status="PSN",
        ability="Iron Fist",
        attack=11,
        defense=10,
        special_attack=11,
        special_defense=10,
        speed=12,
    )
    profile.moves = [
        RuntimeMove("scratch", "Scratch", 32, 35),
        RuntimeMove("leer", "Leer", 30, 30),
        RuntimeMove("ember", "Ember", 25, 25),
    ]
    store.set_party_slot(0, "chimchar")
    store.save()

    loaded = RuntimeStateStore(path)
    chimchar = loaded.profile_for("chimchar")
    assert chimchar is not None
    assert chimchar.hp_fraction == 0.7
    assert chimchar.ability == "Iron Fist"
    assert chimchar.attack == 11
    assert [move.name for move in chimchar.moves] == ["Scratch", "Leer", "Ember"]
    assert loaded.party_slots[0] == "chimchar"
