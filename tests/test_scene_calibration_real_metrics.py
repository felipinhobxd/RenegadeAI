from renegade_ai.perception.scene import SceneType, classify_metrics


def classify(**values):
    metrics = {
        "red": 0.0,
        "blue": 0.0,
        "tan": 0.0,
        "yellow": 0.0,
        "purple": 0.0,
        "dark": 0.0,
        "green": 0.0,
    }
    metrics.update(values)
    return classify_metrics(metrics)[0]


def test_real_command_capture_is_battle_command():
    assert classify(
        red=0.288549,
        blue=0.038087,
        tan=0.008311,
        purple=0.0,
        dark=0.073589,
    ) == SceneType.BATTLE_COMMAND


def test_real_bag_category_capture_is_bag_menu():
    assert classify(
        red=0.0,
        blue=0.022832,
        tan=0.499748,
        yellow=0.042844,
        purple=0.115728,
    ) == SceneType.BAG_MENU


def test_real_party_capture_is_party_menu():
    assert classify(
        red=0.001831,
        blue=0.250153,
        tan=0.032415,
        purple=0.277655,
        dark=0.021424,
    ) == SceneType.PARTY_MENU


def test_real_stats_capture_is_summary_stats():
    assert classify(
        red=0.006961,
        blue=0.500237,
        tan=0.002330,
        purple=0.095290,
        dark=0.036242,
    ) == SceneType.SUMMARY_STATS


def test_summary_moves_does_not_get_confused_with_battle_moves():
    assert classify(
        red=0.011913,
        blue=0.216784,
        tan=0.223381,
        yellow=0.021501,
        purple=0.167167,
        dark=0.003812,
    ) == SceneType.SUMMARY_MOVES


def test_real_battle_move_capture_stays_move_menu():
    assert classify(
        red=0.020546,
        blue=0.181344,
        tan=0.012267,
        yellow=0.060647,
        purple=0.053560,
        dark=0.103847,
    ) == SceneType.MOVE_MENU
