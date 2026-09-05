from types import SimpleNamespace

from renegade_ai.perception.ocr import parse_ocr_result


def test_modern_rapidocr_output_object_is_parsed():
    payload = SimpleNamespace(
        txts=("CHIMCHAR", "14/20"),
        scores=(0.98, 0.94),
        boxes=(
            ((0, 0), (400, 0), (400, 100), (0, 100)),
            ((500, 200), (900, 200), (900, 300), (500, 300)),
        ),
    )
    result = parse_ocr_result(payload, width=1000, height=500)
    assert [line.text for line in result] == ["CHIMCHAR", "14/20"]
    assert result[0].confidence == 0.98
    assert result[0].box == (0.0, 0.0, 0.4, 0.2)
    assert result[1].center == (0.7, 0.5)


def test_legacy_rapidocr_tuple_is_still_supported():
    rows = [
        [((0, 0), (100, 0), (100, 20), (0, 20)), "Ember", 0.91],
    ]
    result = parse_ocr_result((rows, 0.01), width=200, height=100)
    assert len(result) == 1
    assert result[0].text == "Ember"
    assert result[0].confidence == 0.91
