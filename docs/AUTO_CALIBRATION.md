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

## Passive discovery

The scout can also watch normal gameplay and automatically save unknown/new scene transitions:

```powershell
renegade-ai scout --passive-only --watch-seconds 300
```

Unknown screens are named automatically as:

```text
needed_unknown_001
needed_unknown_002
...
```

This creates a calibration inbox for later scene detectors such as item lists, switch confirmation, evolution, badge screens, trainer/boss victory and Hall of Fame/game completion.

You can combine active menu exploration with passive watching:

```powershell
renegade-ai scout --watch-seconds 120
```

## Safety behavior

If the expected scene is not reached, the scout stores what it actually saw in metadata and only uses `B` to retreat through reversible menus. It does not guess by confirming unknown dialogs.

This is intentional: a missing screenshot is preferable to spending a rare item, switching the wrong Pokemon or ending a battle while calibrating.
