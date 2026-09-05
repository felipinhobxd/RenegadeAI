from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from renegade_ai.actions import DSButton
from renegade_ai.campaign.pathfinding import GridPoint
from renegade_ai.memory.platinum import StructuredLocation


@dataclass(slots=True)
class OutcomeStat:
    attempts: int = 0
    successes: int = 0
    blocked: int = 0
    no_effect: int = 0
    map_changes: int = 0
    story_progress: int = 0
    last_seen_at: str = ""

    @property
    def reliability(self) -> float:
        if self.attempts <= 0:
            return 0.5
        return (self.successes + 1.0) / (self.attempts + 2.0)


class CampaignOutcomeMemory:
    """Persistent positive/negative experience for overworld decisions.

    The exact map graph answers *can I move there?*. This layer answers *did
    doing that actually help?*. It learns small, inspectable facts instead of
    changing code or replacing the deterministic Pokemon/world mechanics:

    - moves that repeatedly leave the player on the same tile are bad edges;
    - recently revisited tiles become more expensive to break short loops;
    - NPC/coord-event targets that repeatedly produce no story change are
      deprioritized for the current objective;
    - successful map/story transitions remain preferred evidence.

    Hot-path state is kept in memory and checkpointed in small batches. Failures,
    loop detection, map transitions and objective outcomes force a checkpoint so
    useful negative experience survives a crash without writing a full JSON file
    on every normal walking step.
    """

    def __init__(
        self,
        path: str | Path = Path("data/campaign_outcomes.json"),
        *,
        telemetry_path: str | Path = Path("runs/campaign_telemetry.jsonl"),
        recent_limit: int = 96,
        checkpoint_every: int = 12,
    ) -> None:
        self.path = Path(path)
        self.telemetry_path = Path(telemetry_path)
        self.recent_limit = max(16, int(recent_limit))
        self.checkpoint_every = max(1, int(checkpoint_every))
        self.tile_visits: dict[str, int] = {}
        self.action_stats: dict[str, OutcomeStat] = {}
        self.target_stats: dict[str, OutcomeStat] = {}
        self.recent_states: deque[str] = deque(maxlen=self.recent_limit)
        self.last_story_digest: str | None = None
        self.last_objective_id: str | None = None
        self._dirty_events = 0
        self._load()

    @staticmethod
    def location_key(location: StructuredLocation) -> str:
        return f"{location.map_header_id}:{location.x}:{location.z}"

    @staticmethod
    def point_key(map_id: int, point: GridPoint) -> str:
        return f"{map_id}:{point.x}:{point.z}"

    @staticmethod
    def _objective(value: str | None) -> str:
        return value or "*"

    def _action_key(
        self,
        objective_id: str | None,
        location: StructuredLocation,
        action: DSButton,
    ) -> str:
        return f"{self._objective(objective_id)}|{self.location_key(location)}|{action.value}"

    def _target_key(
        self,
        objective_id: str | None,
        map_id: int,
        point: GridPoint,
        kind: str,
    ) -> str:
        return f"{self._objective(objective_id)}|{map_id}:{point.x}:{point.z}|{kind}"

    @staticmethod
    def _stat(raw: Any) -> OutcomeStat:
        if not isinstance(raw, dict):
            return OutcomeStat()
        allowed = OutcomeStat.__dataclass_fields__
        return OutcomeStat(**{key: value for key, value in raw.items() if key in allowed})

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(payload, dict):
            return
        self.tile_visits = {
            str(key): max(0, int(value))
            for key, value in dict(payload.get("tile_visits", {})).items()
        }
        self.action_stats = {
            str(key): self._stat(value)
            for key, value in dict(payload.get("action_stats", {})).items()
        }
        self.target_stats = {
            str(key): self._stat(value)
            for key, value in dict(payload.get("target_stats", {})).items()
        }
        recent = payload.get("recent_states", [])
        if isinstance(recent, list):
            self.recent_states.extend(str(value) for value in recent[-self.recent_limit :])
        story = payload.get("last_story_digest")
        objective = payload.get("last_objective_id")
        self.last_story_digest = None if story is None else str(story)
        self.last_objective_id = None if objective is None else str(objective)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "tile_visits": self.tile_visits,
            "action_stats": {key: asdict(value) for key, value in self.action_stats.items()},
            "target_stats": {key: asdict(value) for key, value in self.target_stats.items()},
            "recent_states": list(self.recent_states),
            "last_story_digest": self.last_story_digest,
            "last_objective_id": self.last_objective_id,
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.path)
        self._dirty_events = 0

    def _changed(self, *, force: bool = False) -> None:
        self._dirty_events += 1
        if force or self._dirty_events >= self.checkpoint_every:
            self.save()

    def _telemetry(self, event: str, payload: dict[str, Any]) -> None:
        self.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "event": event,
            "created_at": datetime.now(UTC).isoformat(),
            **payload,
        }
        try:
            with self.telemetry_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        except OSError:
            pass

    def observe_state(
        self,
        location: StructuredLocation,
        *,
        objective_id: str | None,
        story_digest: str | None,
    ) -> dict[str, Any]:
        key = self.location_key(location)
        self.tile_visits[key] = self.tile_visits.get(key, 0) + 1
        self.recent_states.append(key)
        story_changed = (
            story_digest is not None
            and self.last_story_digest is not None
            and story_digest != self.last_story_digest
        )
        objective_changed = (
            objective_id is not None
            and self.last_objective_id is not None
            and objective_id != self.last_objective_id
        )
        if story_digest is not None:
            self.last_story_digest = story_digest
        if objective_id is not None:
            self.last_objective_id = objective_id

        window = list(self.recent_states)[-24:]
        unique = len(set(window))
        same_here = sum(1 for value in window if value == key)
        loop_level = 0
        if len(window) >= 8 and unique <= 2:
            loop_level = 3
        elif len(window) >= 12 and unique <= 4:
            loop_level = 2
        elif same_here >= 4:
            loop_level = 1
        if story_changed or objective_changed:
            loop_level = 0
            self.recent_states.clear()
            self.recent_states.append(key)

        result = {
            "state_key": key,
            "story_changed": story_changed,
            "objective_changed": objective_changed,
            "loop_level": loop_level,
            "recent_unique": unique,
            "recent_same_here": same_here,
        }
        important = bool(loop_level or story_changed or objective_changed)
        if important:
            self._telemetry(
                "planner_state",
                {
                    **result,
                    "map_id": location.map_header_id,
                    "x": location.x,
                    "z": location.z,
                    "objective_id": objective_id,
                },
            )
        self._changed(force=important)
        return result

    def record_transition(
        self,
        before: StructuredLocation,
        action: DSButton,
        after: StructuredLocation,
        *,
        objective_id: str | None,
        story_changed: bool = False,
        objective_changed: bool = False,
    ) -> OutcomeStat:
        key = self._action_key(objective_id, before, action)
        stat = self.action_stats.setdefault(key, OutcomeStat())
        stat.attempts += 1
        moved = self.location_key(before) != self.location_key(after)
        map_changed = before.map_header_id != after.map_header_id
        if moved:
            stat.successes += 1
        else:
            stat.blocked += 1
            stat.no_effect += 1
        if map_changed:
            stat.map_changes += 1
        if story_changed or objective_changed:
            stat.story_progress += 1
        stat.last_seen_at = datetime.now(UTC).isoformat()

        # Do not append the destination to recent_states here. The planner's
        # next observe_state() sees it once. Counting both before and after made
        # normal back-and-forth movement look like a loop twice as quickly.
        after_key = self.location_key(after)
        self._telemetry(
            "movement",
            {
                "objective_id": objective_id,
                "before": self.location_key(before),
                "action": action.value,
                "after": after_key,
                "moved": moved,
                "map_changed": map_changed,
                "story_changed": story_changed,
                "objective_changed": objective_changed,
                "attempts": stat.attempts,
                "blocked": stat.blocked,
                "no_effect": stat.no_effect,
            },
        )
        self._changed(force=not moved or map_changed or story_changed or objective_changed)
        return stat

    def action_penalty(
        self,
        objective_id: str | None,
        location: StructuredLocation,
        action: DSButton,
    ) -> float:
        stat = self.action_stats.get(self._action_key(objective_id, location, action))
        if stat is None:
            return 0.0
        return max(
            0.0,
            stat.blocked * 4.0 + stat.no_effect * 2.0 - stat.successes * 1.5,
        )

    def record_target_result(
        self,
        *,
        objective_id: str | None,
        map_id: int,
        point: GridPoint,
        kind: str,
        success: bool,
    ) -> OutcomeStat:
        key = self._target_key(objective_id, map_id, point, kind)
        stat = self.target_stats.setdefault(key, OutcomeStat())
        stat.attempts += 1
        if success:
            stat.successes += 1
            stat.story_progress += 1
        else:
            stat.no_effect += 1
        stat.last_seen_at = datetime.now(UTC).isoformat()
        self._telemetry(
            "target_outcome",
            {
                "objective_id": objective_id,
                "map_id": map_id,
                "x": point.x,
                "z": point.z,
                "kind": kind,
                "success": success,
                "attempts": stat.attempts,
                "no_effect": stat.no_effect,
            },
        )
        self._changed(force=True)
        return stat

    def target_penalty(
        self,
        objective_id: str | None,
        map_id: int,
        point: GridPoint,
        kind: str,
    ) -> float:
        stat = self.target_stats.get(self._target_key(objective_id, map_id, point, kind))
        if stat is None:
            return 0.0
        return max(0.0, stat.no_effect * 12.0 - stat.successes * 8.0)

    def target_suppressed(
        self,
        objective_id: str | None,
        map_id: int,
        point: GridPoint,
        kind: str,
        *,
        threshold: int = 2,
    ) -> bool:
        stat = self.target_stats.get(self._target_key(objective_id, map_id, point, kind))
        return bool(stat and stat.successes == 0 and stat.no_effect >= threshold)

    def tile_penalty(self, map_id: int, point: GridPoint) -> float:
        key = self.point_key(map_id, point)
        lifetime = self.tile_visits.get(key, 0)
        recent = sum(1 for value in self.recent_states if value == key)
        # Sub-linear lifetime cost preserves valid shortest paths; recent visits
        # are more expensive because they indicate an active loop right now.
        return min(3.0, 0.08 * math.sqrt(lifetime)) + min(7.0, recent * 0.65)

    def stats(self) -> dict[str, int]:
        return {
            "tiles": len(self.tile_visits),
            "actions": len(self.action_stats),
            "targets": len(self.target_stats),
            "recent_states": len(self.recent_states),
            "pending_checkpoint_events": self._dirty_events,
        }
