from __future__ import annotations

from dataclasses import dataclass

from renegade_ai.memory.platinum import StructuredProgress, StructuredStoryState


@dataclass(frozen=True, slots=True)
class StoryObjective:
    id: str
    description: str
    target_maps: tuple[str, ...]
    kind: str = "reach"
    interact: bool = False
    target_hint: str | None = None


class StoryObjectivePlanner:
    """Main-story objective selector for a normal Platinum/Renegade run.

    This is deliberately hierarchical. RAM flags/badges provide completion
    evidence; the map planner provides routes. If Renegade changes a local NPC
    or script, the objective remains useful while live RAM/vision can discover
    the changed interaction instead of relying on a brittle prerecorded button
    sequence.
    """

    def __init__(self) -> None:
        self.last_objective_id: str | None = None

    @staticmethod
    def _has_flag(story: StructuredStoryState | None, token: str) -> bool:
        if story is None:
            return False
        token = token.upper()
        return any(token in name.upper() for name in story.active_flags)

    @staticmethod
    def _visited(visited_maps: set[str], *names: str) -> bool:
        return any(name in visited_maps for name in names)

    def choose(
        self,
        *,
        current_map: str,
        progress: StructuredProgress,
        story: StructuredStoryState | None,
        visited_maps: set[str],
    ) -> StoryObjective | None:
        current_map = current_map.upper()
        visited = {name.upper() for name in visited_maps}
        visited.add(current_map)
        badges = progress.badge_count

        if progress.main_story_cleared:
            return None

        # Exact persistent flags are preferred over exploration history for the
        # opening. This matters when RenegadeAI is attached to an existing save:
        # it must not walk back to Sandgem merely because its own map cache was
        # created after the Pokedex was already obtained.
        if badges == 0:
            if not self._has_flag(story, "FLAG_HAS_POKEDEX"):
                return self._remember(
                    StoryObjective(
                        "get_pokedex",
                        "Complete Professor Rowan's lab sequence and obtain the Pokedex",
                        ("SANDGEM_TOWN_POKEMON_RESEARCH_LAB",),
                        interact=True,
                        target_hint="PROF_ROWAN",
                    )
                )
            if not self._has_flag(story, "FLAG_JOURNAL_ACQUIRED"):
                return self._remember(
                    StoryObjective(
                        "return_home_for_journal",
                        "Return home after receiving the Pokedex and get the Journal",
                        ("TWINLEAF_TOWN_PLAYER_HOUSE_1F",),
                        interact=True,
                        target_hint="MOM",
                    )
                )
            if not self._visited(visited, "JUBILIFE_CITY", "OREBURGH_CITY"):
                return self._remember(
                    StoryObjective(
                        "reach_jubilife",
                        "Reach Jubilife City and clear the early city events",
                        ("JUBILIFE_CITY",),
                        interact=True,
                    )
                )
            if not self._visited(visited, "OREBURGH_CITY"):
                return self._remember(
                    StoryObjective(
                        "reach_oreburgh",
                        "Travel through Route 203/Oreburgh Gate to Oreburgh City",
                        ("OREBURGH_CITY",),
                    )
                )
            if not self._has_flag(story, "ROARK_RETURNED_TO_OREBURGH_GYM"):
                return self._remember(
                    StoryObjective(
                        "return_roark",
                        "Find Roark in Oreburgh Mine so he returns to the Gym",
                        ("OREBURGH_MINE_B2F", "OREBURGH_MINE_B1F"),
                        interact=True,
                        target_hint="Roark",
                    )
                )
            return self._remember(
                StoryObjective(
                    "coal_badge",
                    "Defeat Roark and obtain the Coal Badge",
                    ("OREBURGH_CITY_GYM",),
                    kind="badge",
                    interact=True,
                    target_hint="Gym Leader",
                )
            )

        # Badge 1 -> Valley Windworks/Floaroma -> Eterna -> Gardenia.
        if badges == 1:
            if not self._visited(visited, "VALLEY_WINDWORKS_BUILDING", "ETERNA_CITY"):
                if not self._visited(visited, "VALLEY_WINDWORKS_OUTSIDE"):
                    return self._remember(
                        StoryObjective(
                            "valley_windworks",
                            "Resolve the Floaroma/Valley Windworks Galactic incident",
                            ("VALLEY_WINDWORKS_OUTSIDE", "FLOAROMA_MEADOW"),
                            interact=True,
                            target_hint="Galactic grunts / Works Key",
                        )
                    )
                return self._remember(
                    StoryObjective(
                        "clear_windworks",
                        "Enter and clear the Valley Windworks building",
                        ("VALLEY_WINDWORKS_BUILDING",),
                        interact=True,
                    )
                )
            if not self._visited(visited, "ETERNA_CITY"):
                return self._remember(
                    StoryObjective(
                        "reach_eterna",
                        "Cross Route 205 and Eterna Forest to Eterna City",
                        ("ETERNA_CITY",),
                    )
                )
            return self._remember(
                StoryObjective(
                    "forest_badge",
                    "Defeat Gardenia and obtain the Forest Badge",
                    ("ETERNA_CITY_GYM",),
                    kind="badge",
                    interact=True,
                )
            )

        # In Platinum Fantina is the third Gym Leader.
        if badges == 2:
            if not self._visited(visited, "TEAM_GALACTIC_ETERNA_BUILDING_1F"):
                return self._remember(
                    StoryObjective(
                        "eterna_galactic",
                        "Clear the Team Galactic Eterna Building",
                        ("TEAM_GALACTIC_ETERNA_BUILDING_1F",),
                        interact=True,
                    )
                )
            if not self._visited(visited, "HEARTHOME_CITY"):
                return self._remember(
                    StoryObjective(
                        "reach_hearthome",
                        "Travel to Hearthome City",
                        ("HEARTHOME_CITY",),
                    )
                )
            return self._remember(
                StoryObjective(
                    "relic_badge",
                    "Defeat Fantina and obtain the Relic Badge",
                    ("HEARTHOME_CITY_GYM_LEADER_ROOM", "HEARTHOME_CITY_GYM_ENTRANCE_ROOM"),
                    kind="badge",
                    interact=True,
                )
            )

        if badges == 3:
            if not self._visited(visited, "VEILSTONE_CITY"):
                return self._remember(
                    StoryObjective(
                        "reach_veilstone",
                        "Travel through Solaceon/Route 215 to Veilstone City",
                        ("VEILSTONE_CITY",),
                    )
                )
            return self._remember(
                StoryObjective(
                    "cobble_badge",
                    "Defeat Maylene and obtain the Cobble Badge",
                    ("VEILSTONE_CITY_GYM",),
                    kind="badge",
                    interact=True,
                )
            )

        if badges == 4:
            if not self._visited(visited, "PASTORIA_CITY"):
                return self._remember(
                    StoryObjective(
                        "reach_pastoria",
                        "Travel to Pastoria City",
                        ("PASTORIA_CITY",),
                    )
                )
            return self._remember(
                StoryObjective(
                    "fen_badge",
                    "Defeat Crasher Wake and obtain the Fen Badge",
                    ("PASTORIA_CITY_GYM",),
                    kind="badge",
                    interact=True,
                )
            )

        # After Wake the story routes through the Galactic chase/Celestic
        # sequence before Canalave. If Canalave has already been reached, don't
        # force a completed detour again.
        if badges == 5:
            if not self._visited(visited, "CELESTIC_TOWN", "CANALAVE_CITY"):
                return self._remember(
                    StoryObjective(
                        "celestic_story",
                        "Follow the Galactic/Cynthia story through Route 210 to Celestic Town",
                        ("CELESTIC_TOWN",),
                        interact=True,
                    )
                )
            if not self._visited(visited, "CANALAVE_CITY"):
                return self._remember(
                    StoryObjective(
                        "reach_canalave",
                        "Reach Canalave City",
                        ("CANALAVE_CITY",),
                    )
                )
            return self._remember(
                StoryObjective(
                    "mine_badge",
                    "Defeat Byron and obtain the Mine Badge",
                    ("CANALAVE_CITY_GYM",),
                    kind="badge",
                    interact=True,
                )
            )

        if badges == 6:
            if not self._visited(visited, "SNOWPOINT_CITY"):
                return self._remember(
                    StoryObjective(
                        "reach_snowpoint",
                        "Complete the lake story and travel north to Snowpoint City",
                        ("SNOWPOINT_CITY",),
                        interact=True,
                    )
                )
            return self._remember(
                StoryObjective(
                    "icicle_badge",
                    "Defeat Candice and obtain the Icicle Badge",
                    ("SNOWPOINT_CITY_GYM",),
                    kind="badge",
                    interact=True,
                )
            )

        if badges == 7:
            # Post-Snowpoint story: Lake Acuity -> Galactic HQ -> Spear Pillar
            # -> Distortion World -> Sunyshore.
            if not self._visited(visited, "LAKE_ACUITY", "GALACTIC_HQ_1F"):
                return self._remember(
                    StoryObjective(
                        "lake_acuity",
                        "Resolve the Lake Acuity story after the seventh badge",
                        ("LAKE_ACUITY",),
                        interact=True,
                    )
                )
            if not self._visited(visited, "GALACTIC_HQ_1F", "SPEAR_PILLAR"):
                return self._remember(
                    StoryObjective(
                        "galactic_hq",
                        "Infiltrate and clear Team Galactic HQ in Veilstone",
                        ("GALACTIC_HQ_1F",),
                        interact=True,
                    )
                )
            if not self._visited(
                visited,
                "SPEAR_PILLAR",
                "DISTORTION_WORLD_1F",
                "SUNYSHORE_CITY",
            ):
                return self._remember(
                    StoryObjective(
                        "spear_pillar",
                        "Ascend Mt. Coronet and resolve the Spear Pillar event",
                        ("SPEAR_PILLAR", "SPEAR_PILLAR_DISTORTED"),
                        interact=True,
                    )
                )
            if not self._visited(visited, "DISTORTION_WORLD_1F", "SUNYSHORE_CITY"):
                return self._remember(
                    StoryObjective(
                        "distortion_world",
                        "Traverse the Distortion World and complete the Giratina/Cyrus event",
                        (
                            "DISTORTION_WORLD_1F",
                            "DISTORTION_WORLD_B1F",
                            "DISTORTION_WORLD_B2F",
                            "DISTORTION_WORLD_B3F",
                            "DISTORTION_WORLD_B4F",
                            "DISTORTION_WORLD_B5F",
                            "DISTORTION_WORLD_B6F",
                            "DISTORTION_WORLD_B7F",
                            "DISTORTION_WORLD_GIRATINA_ROOM",
                        ),
                        interact=True,
                    )
                )
            if not self._visited(visited, "SUNYSHORE_CITY"):
                return self._remember(
                    StoryObjective(
                        "reach_sunyshore",
                        "Travel to Sunyshore City",
                        ("SUNYSHORE_CITY",),
                    )
                )
            return self._remember(
                StoryObjective(
                    "beacon_badge",
                    "Defeat Volkner and obtain the Beacon Badge",
                    (
                        "SUNYSHORE_CITY_GYM_ROOM_1",
                        "SUNYSHORE_CITY_GYM_ROOM_2",
                        "SUNYSHORE_CITY_GYM_ROOM_3",
                    ),
                    kind="badge",
                    interact=True,
                )
            )

        # Eight badges: Victory Road -> Pokemon League -> Hall of Fame.
        if not self._visited(visited, "VICTORY_ROAD_1F", "POKEMON_LEAGUE"):
            return self._remember(
                StoryObjective(
                    "victory_road",
                    "Reach and traverse Victory Road",
                    (
                        "VICTORY_ROAD_1F",
                        "VICTORY_ROAD_2F",
                        "VICTORY_ROAD_B1F",
                    ),
                    interact=True,
                )
            )
        if not self._visited(visited, "POKEMON_LEAGUE"):
            return self._remember(
                StoryObjective(
                    "reach_league",
                    "Reach the Pokemon League",
                    ("POKEMON_LEAGUE",),
                )
            )
        return self._remember(
            StoryObjective(
                "hall_of_fame",
                "Defeat the Elite Four and Champion Cynthia to enter the Hall of Fame",
                (
                    "POKEMON_LEAGUE_AARON_ROOM",
                    "POKEMON_LEAGUE_BERTHA_ROOM",
                    "POKEMON_LEAGUE_FLINT_ROOM",
                    "POKEMON_LEAGUE_LUCIAN_ROOM",
                    "POKEMON_LEAGUE_CHAMPION_ROOM",
                    "POKEMON_LEAGUE_HALL_OF_FAME",
                ),
                kind="game_complete",
                interact=True,
            )
        )

    def _remember(self, objective: StoryObjective) -> StoryObjective:
        self.last_objective_id = objective.id
        return objective
