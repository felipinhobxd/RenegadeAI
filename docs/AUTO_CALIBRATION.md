# Autonomous calibration screenshot scout

RenegadeAI can now collect the screenshots needed for new UI calibration itself.

## Recommended use

Start on the four-option battle command screen (`LUTAR / MOCHILA / FUGIR / POKEMON`) and run:

```powershell
renegade-ai scout
```

The scout navigates only reversible calibration paths. It does **not**:

- touch `FUGIR`;
- select a battle move;
- select/use a Bag item;
- confirm a Pokemon switch.

It currently captures and names:

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

For every capture it writes:

```text
<target>__seen-<detected-scene>__<timestamp>.png
<target>__seen-<detected-scene>__<timestamp>__viewport.png
<target>__seen-<detected-scene>__<timestamp>__top.png
<target>__seen-<detected-scene>__<timestamp>__bottom.png
<target>__seen-<detected-scene>__<timestamp>.json
```

A shared `manifest.json` records what was captured, what the classifier thought the screen was, its confidence/color metrics and which currently required targets are still missing.

Default output:

```text
captures/auto-calibration/
```

The whole `captures/` directory is ignored by Git.

## Passive semantic discovery

The scout can also watch normal gameplay and automatically save unknown/new scene transitions:

```powershell
renegade-ai scout --passive-only --watch-seconds 300
```

For an unknown screen it first runs OCR and tries to assign a useful semantic name. Current high-confidence semantic labels include:

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

If OCR cannot safely identify the screen, it falls back to a calibration-inbox name:

```text
needed_unknown_001
needed_unknown_002
...
```

This means new screens are preserved even when RenegadeAI does not understand them yet, while recognizable screens receive names based on what is actually visible instead of a manual filename.

Recognized campaign milestones are also connected to ASI-Evolve. Capture, level-up, evolution, badge, boss-victory and Hall of Fame/game-completion messages can create persistent rewards. Repeated frames of the same visible message are deduplicated; game completion is rewarded only once per learning profile.

You can combine active menu exploration with passive watching:

```powershell
renegade-ai scout --watch-seconds 120
```

## Safety behavior

If the expected scene is not reached, the scout stores what it actually saw in metadata and only uses `B` to retreat through reversible menus. It does not guess by confirming unknown dialogs.

This is intentional: a missing screenshot is preferable to spending a rare item, switching the wrong Pokemon or ending a battle while calibrating.
