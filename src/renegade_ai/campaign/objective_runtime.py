from __future__ import annotations

from typing import Any

from renegade_ai.campaign.live_progression import LiveProgressionDirector
from renegade_ai.campaign.smart_runtime import SmartCampaignAutopilot
from renegade_ai.perception.frame import DSScreens, split_ds_screens
from renegade_ai.perception.scene import SceneType, detect_scene


def _looks_like_dialogue_box(image: Any) -> bool:
    """Cheap pre-OCR cue for Platinum's upper-screen dialogue box.

    Dialogue can begin automatically while the lower Poketch still resembles
    the normal overworld. A light, low-saturation rectangle with dark glyphs in
    the lower part of the upper DS screen is only a cue: OCR still has to
    confirm readable dialogue before any A press is issued.
    """
    import numpy as np

    rgb = np.asarray(image)[..., :3].astype(np.int16)
    if rgb.size == 0:
        return False
    height, width = rgb.shape[:2]
    region = rgb[int(height * 0.58) : int(height * 0.97), int(width * 0.02) : int(width * 0.98)]
    if region.size == 0:
        return False
    maximum = region.max(axis=2)
    minimum = region.min(axis=2)
    mean = region.mean(axis=2)
    neutral_light = (maximum - minimum < 55) & (mean > 125)
    dark_ink = maximum < 95
    return float(neutral_light.mean()) >= 0.32 and float(dark_ink.mean()) >= 0.012


class ObjectiveCampaignAutopilot(SmartCampaignAutopilot):
    """Full campaign loop with goal routing and proactive dialogue detection."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Preserve the world/objective caches created by the base class while
        # upgrading portal selection to prefer transitions actually observed in
        # the user's running Renegade Platinum save.
        self.progression = LiveProgressionDirector(
            world=self.progression.world,
            objectives=self.progression.objectives,
        )

    def _explore_once(self, screens: DSScreens) -> tuple[int, SceneType]:
        # Detect dialogue BEFORE issuing a movement command. The older recovery
        # path already checked dialogue after a failed move; this removes that
        # wasted direction press for automatic NPC/story conversations.
        if _looks_like_dialogue_box(screens.top):
            advanced, _lines = self._advance_dialogue(screens)
            if advanced:
                scene = detect_scene(
                    split_ds_screens(self.emulator.capture(), self.screen_layout)
                ).scene
                return 1, scene
        return super()._explore_once(screens)
