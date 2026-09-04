# ASI-Evolve mode

`ASI-Evolve` is the project name for RenegadeAI's persistent self-improving policy. It is **not a claim of literal ASI**. The implementation is a mechanics-first reinforcement-learning layer that learns from outcomes while keeping deterministic Pokemon rules as the primary planner.

## Reward hierarchy

The engine stores rewards at several time scales.

| Outcome | Default reward |
| --- | ---: |
| Deal 100% of an opponent's HP | +120 |
| Lose 100% of own HP | -90 |
| Opponent KO | +35 |
| Own Pokemon faints | -70 |
| Inflict a major status | +12 |
| Receive a major status | -15 |
| Win a battle | +100 |
| Lose a battle | -120 |
| Successful capture | +45 |
| Level up | +20 |
| Evolution | +70 |
| Add a new species | +35 |
| Good switch | +18 |
| Efficient heal | +15 |
| Waste an item | -25 |
| Objective progress | +80 |
| Trainer win | +140 |
| Boss win | +400 |
| Badge | +600 |
| Finish the game / Hall of Fame | +5000 |

Continuous rewards such as damage use the observed fraction. Dealing 50% HP therefore starts from `0.50 * 120 = +60` before other turn outcomes are considered.

## Why the learned policy is bounded

RenegadeAI does not let a noisy reward erase known game mechanics. Battle move ranking still begins with type effectiveness, STAB, actual stats when known, move power, accuracy, PP, ability/item/status mechanics and estimated damage.

Learned history only supplies a bounded correction. It also needs repeated evidence before reaching full confidence. Live saves use no random exploration (`epsilon = 0`), so the agent does not intentionally make bad moves just to experiment.

This reduces reward hacking and prevents one lucky Ember, one OCR mistake or a huge campaign milestone from permanently making an unrelated move dominate the simulator.

## Persistent files

The default local learning files are:

```text
data/battle_adaptive.json
data/evolve_state.json
data/evolve_qtable.json
data/evolve_rewards.jsonl
```

They are ignored by Git. `evolve_rewards.jsonl` is the auditable event ledger; `evolve_state.json` contains generation/fitness/counters; the Q-table contains state-action experience.

## Commands

Run a learning battle:

```powershell
renegade-ai evolve battle --max-seconds 180
```

Inspect accumulated progress:

```powershell
renegade-ai evolve status
```

The generation number advances every 100 observed reward events. This is a tracking concept, not opaque code mutation.

## Future automatic milestone detectors

The reward API already supports capture, level-up, evolution, new species, trainer/boss wins, badges, objectives and game completion. Those rewards become automatic as perception modules for the corresponding screens/events are added.

The autonomous screenshot scout exists specifically to collect those unknown UI states without requiring manual screenshots.
