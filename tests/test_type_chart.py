from renegade_ai.strategy.type_chart import effectiveness


def test_dual_type_effectiveness_multiplies():
    assert effectiveness("fire", ("grass", "ice")) == 4.0
    assert effectiveness("electric", ("water", "flying")) == 4.0


def test_immunities_are_respected():
    assert effectiveness("normal", ("ghost",)) == 0.0
    assert effectiveness("dragon", ("fairy",)) == 0.0
    assert effectiveness("electric", ("ground", "water")) == 0.0
