# Autonomous calibration screenshot scout

RenegadeAI can collect the screenshots needed for new UI calibration itself.

## Normal v0.5 workflow: no scout command

When the Windows autoplay watcher is installed, calibration is part of the campaign loop. Open melonDS and load the game; the director automatically saves novel scenes and, at safe battle-command screens, can enter reversible menus to collect currently missing Bag/party calibration captures.

Default output:

```text
captures/auto-calibration/
```

The whole `captures/` directory is ignored by Git.

## What it can safely explore

From the four-option battle command screen (`LUTAR / MOCHILA / FUGIR / POKEMON`) the scout can capture/name:

```text
battle_command
battle_move_menu
bag_categories
bag_restore_list
bag_pokeballs_list
bag_status_list
bag_battle_items_list
battle_party
party_slot_action_menu
```

The calibration explorer does **not**:

- touch `FUGIR`;
- select a battle move;
- select/use a Bag item;
- confirm a Pokemon switch.

For every capture it can write:

```text
<target>__seen-<detected-scene>__<timestamp>.png
<target>__seen-<detected-scene>__<timestamp>__viewport.png
<target>__seen-<detected-scene>__<timestamp>__top.png
<target>__seen-<detected-scene>__<timestamp>__bottom.png
<target>__seen-<detected-scene>__<timestamp>.json
```

A shared `manifest.json` records what was captured, what the classifier thought the screen was, confidence/color metrics and which currently requested targets are still missing.

## Semantic discovery

Unknown screens are OCR-scanned when useful. High-confidence text patterns can automatically assign labels such as:

```text
bag_restore_list
bag_pokeballs_list
bag_status_list
bag_battle_items_list
party_slot_action_menu
capture_success
level_up
evolution
badge_received
boss_victory
game_complete
```

Campaign milestones can also feed ASI-Evolve rewards. Repeated frames are deduplicated so leaving a message visible does not repeatedly award the same event.

If semantic evidence is insufficient, the capture is intentionally left as a calibration-inbox entry:

```text
needed_unknown_001
needed_unknown_002
...
```

A cautious unknown label is preferable to teaching the agent the wrong screen meaning.

## Manual scout mode remains available

For development/debugging, start on the battle command screen and run:

```powershell
renegade-ai scout
```

Or passively watch normal gameplay:

```powershell
renegade-ai scout --passive-only --watch-seconds 300
```

These commands are optional in the v0.5 autoplay workflow.

## Safety behavior

If the expected scene is not reached, the scout stores what it actually saw in metadata and only uses reversible/back-out behavior. It does not guess by confirming unknown dialogs.

This is intentional: a missing screenshot is preferable to spending a rare item, switching the wrong Pokemon or ending a battle while calibrating.
