from renegade_ai.campaign.objectives import StoryObjectivePlanner
from renegade_ai.memory.platinum import StructuredProgress, StructuredStoryState


def progress(badges: int, *, cleared: bool = False) -> StructuredProgress:
    return StructuredProgress(
        badge_mask=(1 << badges) - 1 if badges else 0,
        badge_count=badges,
        money=3000,
        main_story_cleared=cleared,
        has_national_dex=False,
    )


def story(*flags: str) -> StructuredStoryState:
    return StructuredStoryState(
        digest="test",
        active_flag_ids=tuple(range(len(flags))),
        active_flags=flags,
        nonzero_vars={},
    )


def test_opening_requires_pokedex_then_journal():
    planner = StoryObjectivePlanner()
    objective = planner.choose(
        current_map="SANDGEM_TOWN",
        progress=progress(0),
        story=story(),
        visited_maps={"SANDGEM_TOWN"},
    )
    assert objective is not None
    assert objective.id == "get_pokedex"
    assert objective.target_maps == ("SANDGEM_TOWN_POKEMON_RESEARCH_LAB",)

    objective = planner.choose(
        current_map="SANDGEM_TOWN",
        progress=progress(0),
        story=story("FLAG_HAS_POKEDEX"),
        visited_maps={"SANDGEM_TOWN"},
    )
    assert objective is not None
    assert objective.id == "return_home_for_journal"


def test_zero_badges_routes_to_roark_mine_before_gym():
    planner = StoryObjectivePlanner()
    opening_flags = ("FLAG_HAS_POKEDEX", "FLAG_JOURNAL_ACQUIRED")
    objective = planner.choose(
        current_map="OREBURGH_CITY",
        progress=progress(0),
        story=story(*opening_flags),
        visited_maps={"SANDGEM_TOWN", "JUBILIFE_CITY", "OREBURGH_CITY"},
    )
    assert objective is not None
    assert objective.id == "return_roark"
    assert "OREBURGH_MINE_B2F" in objective.target_maps

    objective = planner.choose(
        current_map="OREBURGH_CITY",
        progress=progress(0),
        story=story(*opening_flags, "FLAG_ROARK_RETURNED_TO_OREBURGH_GYM"),
        visited_maps={"SANDGEM_TOWN", "JUBILIFE_CITY", "OREBURGH_CITY"},
    )
    assert objective is not None
    assert objective.id == "coal_badge"


def test_badge_count_moves_main_target_forward():
    planner = StoryObjectivePlanner()
    objective = planner.choose(
        current_map="HEARTHOME_CITY",
        progress=progress(3),
        story=story(),
        visited_maps={"HEARTHOME_CITY"},
    )
    assert objective is not None
    assert objective.id == "reach_veilstone"

    objective = planner.choose(
        current_map="VEILSTONE_CITY",
        progress=progress(3),
        story=story(),
        visited_maps={"HEARTHOME_CITY", "VEILSTONE_CITY"},
    )
    assert objective is not None
    assert objective.id == "cobble_badge"


def test_story_complete_has_no_remaining_objective():
    planner = StoryObjectivePlanner()
    assert planner.choose(
        current_map="POKEMON_LEAGUE_HALL_OF_FAME",
        progress=progress(8, cleared=True),
        story=story(),
        visited_maps={"POKEMON_LEAGUE_HALL_OF_FAME"},
    ) is None
