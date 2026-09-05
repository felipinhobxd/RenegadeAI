import json
import struct

from renegade_ai.campaign.pathfinding import GridPoint
from renegade_ai.campaign.world_model import PlatinumWorldModel
from renegade_ai.memory.platinum import MapHeaderCatalog


def _catalog(tmp_path):
    catalog = MapHeaderCatalog(tmp_path / "headers.json")
    catalog.names = [
        "MAP_HEADER_EVERYWHERE",
        "MAP_HEADER_NOTHING",
        "MAP_HEADER_UNDERGROUND",
        "MAP_HEADER_ALPHA",
        "MAP_HEADER_BETA",
    ]
    return catalog


def _land_file(path, *, collision_index=None):
    data = bytearray(0x10 + 0x800)
    struct.pack_into("<4I", data, 0, 0x800, 0, 0, 0)
    if collision_index is not None:
        struct.pack_into("<H", data, 0x10 + collision_index * 2, 0x8000)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_world_model_reads_platinum_collision_bit_and_matrix_adjacency(tmp_path):
    model = PlatinumWorldModel(tmp_path / "world", catalog=_catalog(tmp_path))
    model._matrices = {
        0: {
            "headers": [["MAP_HEADER_ALPHA", "MAP_HEADER_BETA"]],
            "land_data_maps": [[10, 11]],
        }
    }
    model._rebuild_indexes()
    _land_file(model.root / "land" / "map_010.bin", collision_index=5)
    _land_file(model.root / "land" / "map_011.bin")

    assert model.is_colliding(3, 5, 0) is True
    assert model.is_colliding(3, 4, 0) is False
    assert 4 in model.map_neighbors(3)
    assert model.map_route(3, {4}) == [3, 4]


def test_world_model_loads_static_warp_coordinates(tmp_path):
    model = PlatinumWorldModel(tmp_path / "world", catalog=_catalog(tmp_path))
    event_path = model.root / "events" / "events_alpha.json"
    event_path.write_text(
        json.dumps(
            {
                "warp_events": [
                    {
                        "x": 7,
                        "z": 9,
                        "dest_header_id": "MAP_HEADER_BETA",
                        "dest_warp_id": 2,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    warps = model.warps(3)
    assert len(warps) == 1
    assert warps[0].source == GridPoint(7, 9)
    assert warps[0].destination_header_id == 4
    assert warps[0].destination_warp_id == 2
