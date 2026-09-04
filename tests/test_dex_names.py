from renegade_ai.knowledge.dex import normalize_name


def test_nidoran_gender_symbols_do_not_collapse_to_same_key():
    female = normalize_name("Nidoran♀")
    male = normalize_name("Nidoran♂")
    assert female == "nidoranfemale"
    assert male == "nidoranmale"
    assert female != male


def test_gender_words_and_symbols_normalize_equivalently():
    assert normalize_name("Nidoran ♀") == normalize_name("Nidoran female")
    assert normalize_name("Nidoran ♂") == normalize_name("Nidoran male")
