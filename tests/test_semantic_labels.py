from renegade_ai.perception.semantic import infer_semantic_label


def test_semantic_bag_labels():
    assert infer_semantic_label(["RESTAURAR PS/PP"]) == "bag_restore_list"
    assert infer_semantic_label(["POKÉBOLAS"]) == "bag_pokeballs_list"
    assert infer_semantic_label(["ESTADO E MEDICAMENTOS"]) == "bag_status_list"
    assert infer_semantic_label(["ITENS DE LUTA"]) == "bag_battle_items_list"


def test_semantic_campaign_milestones():
    assert infer_semantic_label(["PARABÉNS!", "HALL OF FAME"]) == "game_complete"
    assert infer_semantic_label(["Seu Pokémon evoluiu para Monferno!"]) == "evolution"
    assert infer_semantic_label(["Chimchar subiu para o nível 6!"]) == "level_up"
    assert infer_semantic_label(["Pikachu foi capturado!"]) == "capture_success"


def test_ambiguous_text_stays_unknown():
    assert infer_semantic_label(["O que CHIMCHAR vai fazer?"]) is None
