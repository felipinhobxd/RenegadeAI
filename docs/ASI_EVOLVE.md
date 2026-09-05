# ASI-Evolve

`ASI-Evolve` is the project name for RenegadeAI's persistent self-improving policy layer. It is **not** a claim that the program is a literal artificial superintelligence.

The design is mechanics-first: known Pokemon rules remain the main decision signal, while observed outcomes make bounded corrections and long-horizon campaign events shape fitness.

## Reward hierarchy

Examples of reward/penalty families include:

- damage dealt: positive, scaled by opponent HP removed;
- damage taken: negative, scaled by own HP lost;
- opponent KO: positive;
- own faint: negative;
- status inflicted/received;
- good/bad net tactical turns;
- battle win/loss;
- capture;
- level-up;
- evolution;
- efficient healing / bad resource use hooks;
- objective/trainer/boss progress;
- badges;
- Hall of Fame / game completion.

Large campaign milestones are intentionally much more valuable than tiny tactical gains, but individual action-learning updates are clipped so one huge milestone cannot permanently make an unrelated move dominate battle mechanics.

## Persistent confidence

The engine stores:

```text
data/evolve_state.json
data/evolve_qtable.json
data/evolve_rewards.jsonl
data/battle_adaptive.json
```

Repeated evidence increases confidence in a learned correction. One lucky outcome should not override deterministic type/damage reasoning.

These files are local runtime state and are ignored by Git.

## Campaign integration in v0.5

ASI-Evolve now sits underneath the unattended `CampaignAutopilot` as well as the battle agent.

During normal autoplay:

1. the bot observes the live melonDS game;
2. battles produce tactical rewards from HP/status/KO outcomes;
3. OCR/scout perception can identify milestones such as level-up, evolution, badge and game completion;
4. milestone events are deduplicated and written to the reward ledger;
5. campaign exploration state persists separately in `data/campaign_map.json`;
6. future route/objective policies can use the same reward history without relearning basic Pokemon mechanics.

## No random live-save exploration

The battle policy uses no random action exploration. Overworld v0.5 exploration is also deterministic: it prefers untried directions and known paths to unexplored frontiers.

This matters because a real campaign save contains irreversible or costly choices. Training techniques that deliberately try arbitrary actions are better suited to copied savestates/training environments, not the user's primary run.

## Manual diagnostics

Autoplay handles learning automatically, but development commands remain available:

```powershell
renegade-ai evolve battle --max-seconds 180
renegade-ai evolve status
```

A missing Renegade knowledge cache is now built automatically on the first battle/autoplay run.

## Next evolution layer

The largest expected improvement will come from giving the campaign policy reliable structured state (map ID, position, collisions, warps, objectives/story flags) and then rewarding efficient progress between high-level objectives.

This is preferable to simply increasing reward complexity on a pixel-only random explorer. Public Pokemon-agent research consistently shows that long-horizon completion benefits from hierarchical planning, memory and navigation scaffolding; see `AUTOPLAY_RESEARCH.md`.
