from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable


def normalize_ui_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace("é", "e")
    return re.sub(r"[^a-z0-9/ ]+", " ", value)


def _contains(text: str, *phrases: str) -> bool:
    return any(normalize_ui_text(phrase) in text for phrase in phrases)


def infer_semantic_label(lines: Iterable[str]) -> str | None:
    """Infer a useful calibration label from OCR text.

    Rules intentionally prefer high-precision phrases. A wrong semantic label is
    worse than an `unknown` capture because these labels also become future
    reward/calibration hooks.
    """
    text = " ".join(normalize_ui_text(line) for line in lines if line)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None

    # Long-horizon campaign milestones first.
    hall = _contains(text, "hall of fame", "salao da fama")
    champion = _contains(text, "champion", "campeao", "campea")
    congratulations = _contains(text, "congratulations", "parabens")
    if hall or (champion and congratulations):
        return "game_complete"

    if _contains(
        text,
        "recebeu a medalha",
        "obteve a medalha",
        "ganhou a medalha",
        "received the badge",
        "got the badge",
    ):
        return "badge_received"

    if _contains(text, "evoluiu para", "evolved into", "is evolving"):
        return "evolution"

    if _contains(
        text,
        "subiu para o nivel",
        "subiu de nivel",
        "grew to level",
        "leveled up",
        "level up",
    ):
        return "level_up"

    if _contains(
        text,
        "foi capturado",
        "pokemon capturado",
        "gotcha",
        "was caught",
        "was captured",
    ):
        return "capture_success"

    if _contains(text, "derrotou", "venceu", "defeated") and _contains(
        text, "lider", "leader", "elite", "champion", "campeao"
    ):
        return "boss_victory"

    # Known Bag/UI families. This lets a passive capture get a meaningful name
    # even when the color-based scene classifier still reports UNKNOWN.
    if _contains(text, "restaurar ps/pp", "restaurar ps", "restore hp", "restore pp"):
        return "bag_restore_list"
    if _contains(text, "pokebolas", "poke bolas", "poke balls", "pokeballs"):
        return "bag_pokeballs_list"
    if _contains(text, "estado e medicamentos", "medicamentos", "status medicine"):
        return "bag_status_list"
    if _contains(text, "itens de luta", "battle items"):
        return "bag_battle_items_list"
    if _contains(text, "trocar", "switch") and _contains(
        text, "dados", "summary", "movimentos", "moves"
    ):
        return "party_slot_action_menu"

    return None
