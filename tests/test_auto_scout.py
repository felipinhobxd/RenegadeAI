import json

import numpy as np

from renegade_ai.perception.scout import CALIBRATION_NEEDS, AutoCalibrationScout


class FakeEmulator:
    def __init__(self):
        self.frame = np.zeros((384, 256, 3), dtype=np.uint8)

    def capture(self):
        return self.frame.copy()

    def press(self, button, duration=None):
        return None

    def touch_bottom(self, x, y):
        return None


def test_required_capture_is_named_and_removed_from_missing(tmp_path):
    scout = AutoCalibrationScout(FakeEmulator(), root=tmp_path, settle_seconds=0.15)
    record = scout.save("bag_restore_list")
    assert record is not None
    assert record.required is True
    assert "bag_restore_list" in record.full
    assert "bag_restore_list" not in scout.missing()
    assert set(scout.missing()) == set(CALIBRATION_NEEDS) - {"bag_restore_list"}

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert "bag_restore_list" in manifest["captured_needed"]
    assert manifest["safety"]["uses_items"] is False
    assert manifest["safety"]["switches_pokemon"] is False


def test_duplicate_same_target_and_pixels_is_suppressed(tmp_path):
    scout = AutoCalibrationScout(FakeEmulator(), root=tmp_path, settle_seconds=0.15)
    first = scout.save("bag_pokeballs_list")
    second = scout.save("bag_pokeballs_list")
    assert first is not None
    assert second is None
