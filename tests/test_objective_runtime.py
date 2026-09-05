import numpy as np

from renegade_ai.campaign.objective_runtime import _looks_like_dialogue_box


def test_dialogue_box_cue_detects_light_box_with_dark_text():
    image = np.zeros((192, 256, 3), dtype=np.uint8)
    image[112:186, 5:251] = 220
    image[135:145, 35:210] = 40
    image[157:167, 55:220] = 50

    assert _looks_like_dialogue_box(image) is True


def test_dialogue_box_cue_rejects_plain_dark_overworld():
    image = np.full((192, 256, 3), 55, dtype=np.uint8)
    assert _looks_like_dialogue_box(image) is False
