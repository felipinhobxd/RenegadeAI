# RenegadeAI architecture

RenegadeAI is a hybrid autonomous agent for Pokemon Renegade Platinum on melonDS.

```text
                         +----------------------+
                         |   melonDS / game     |
                         +----------+-----------+
                                    |
                     +--------------+--------------+
                     |                             |
             RGB screenshots                 ARM9 GDB reads
                     |                             |
             viewport / OCR              validated Platinum state
                     |                 map/X/Z/story/NPC/progress
                     +--------------+--------------+
                                    |
                         Campaign state fusion
                                    |
             +----------------------+----------------------+
             |                      |                      |
       battle planner       structured navigator      visual fallback
             |                      |                      |
       Renegade Dex          exact coordinate graph    visual topo graph
             |                      |                      |
             +----------------------+----------------------+
                                    |
                              ASI-Evolve
                         bounded outcome memory
                                    |
                         DS buttons / touch input
```

## Trust hierarchy

1. validated structured game state for facts that can be read safely;
2. deterministic Pokemon mechanics / Renegade data;
3. calibrated visual/OCR perception;
4. bounded learned corrections from prior outcomes;
5. conservative fallback behavior when confidence is insufficient.

The agent should not invent a map/Pokemon/action when the relevant layer has low confidence.

## Structured-memory backend

The v0.6 ARM9 backend is read-only with respect to emulated RAM/registers. It uses melonDS' GDB stub to read a validated subset of Platinum's `SaveData` structures. It currently exposes exact location, progress, persistent story variables/flags and persisted field-object hints.

Exact movement creates a persistent `(map_header_id, x, z)` graph. Known object coordinates can turn a failed movement into an interaction attempt rather than a false wall. Structured state failure never blocks the run: the visual navigator remains available.

See `STRUCTURED_MEMORY.md` for validation details.

## Campaign planner direction

The next major navigation layer is objective-aware routing:

```text
story vars/flags -> current objective -> target map/warp/object
                                      -> collision/warp graph
                                      -> A* route
                                      -> visual verification
```

This is preferred over reward-only random exploration because Pokemon is a long-horizon task with many event prerequisites.

## Battle planner

Battle decisions combine synced Renegade data, actual perceived/scanned Pokemon state, Generation IV mechanics approximations and bounded learned matchup corrections. Learning must not override type immunities, unavailable PP or other deterministic mechanics.

## Persistence

Generated/runtime state stays outside Git under `data/`, `captures/` and `runs/` where applicable. ROMs, BIOS/firmware, saves and extracted copyrighted assets are never committed.
