import json
import struct

from renegade_ai.campaign.pathfinding import GridPoint
from renegade_ai.campaign.world_model import MapHeaderMetadata, PlatinumWorldModel
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


def test_world_model_reads_real_pret_maps_key_collision_and_matrix_adjacency(tmp_path):
    model = PlatinumWorldModel(tmp_path / "world", catalog=_catalog(tmp_path))
    model._matrices = {
        0: {
            "headers": [["MAP_HEADER_ALPHA", "MAP_HEADER_BETA"]],
            "maps": [["MAP_010", "MAP_011"]],
        }
    }
    model._rebuild_indexes()
    model.ensure_matrix_index = lambda: True
    _land_file(model.root / "land" / "map_data_010.bin", collision_index=5)
    _land_file(model.root / "land" / "map_data_011.bin")

    assert model.is_colliding(3, 5, 0) is True
    assert model.is_colliding(3, 4, 0) is False
    assert 4 in model.map_neighbors(3)
    assert model.map_route(3, {4}) == [3, 4]


def test_world_model_assigns_header_to_interior_matrix_without_header_section(tmp_path):
    model = PlatinumWorldModel(tmp_path / "world", catalog=_catalog(tmp_path))
    model._header_metadata = {
        3: MapHeaderMetadata(matrix_id=122, events_name="events_alpha")
    }
    model._matrices = {
        122: {
            "headers": [],
            "maps": [["MAP_010"]],
        }
    }
    model._rebuild_indexes()
    model.ensure_matrix_index = lambda: True
    _land_file(model.root / "land" / "map_data_010.bin", collision_index=7)

    assert model.matrix_cell_for(3, 7, 0) is not None
    assert model.is_colliding(3, 7, 0) is True
    assert model.is_colliding(3, 6, 0) is False


def test_world_model_parses_real_land_value_names():
    assert PlatinumWorldModel._land_value("MAP_001") == 1
    assert PlatinumWorldModel._land_value("map_data_665.bin") == 665
    assert PlatinumWorldModel._land_value(17) == 17


def test_world_model_loads_static_warp_coordinates_using_header_event_metadata(tmp_path):
    model = PlatinumWorldModel(tmp_path / "world", catalog=_catalog(tmp_path))
    model._header_metadata = {
        3: MapHeaderMetadata(matrix_id=1, events_name="events_custom_alpha")
    }
    event_path = model.root / "events" / "events_custom_alpha.json"
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
