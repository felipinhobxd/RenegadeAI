# Sources

RenegadeAI keeps downloaded/generated knowledge out of Git and records the public projects used as technical references.

## Renegade Platinum data

The knowledge sync downloads public Renegade Platinum documentation at runtime and pins the external revision used to generate local data. Generated Pokemon/move/strategy JSON and sprite caches live under `data/` and are ignored by Git.

The repository does **not** include a Renegade Platinum ROM, a Pokemon Platinum ROM, BIOS/firmware, save files, savestates or extracted copyrighted game assets.

## melonDS structured access

- melonDS — https://github.com/melonDS-emu/melonDS
- Pokemon Platinum decompilation — https://github.com/pret/pokeplatinum
- Platinum Lua/QoL memory tooling — https://github.com/hzla/Pokemon-Lua

The v0.6 ARM9 backend uses melonDS' GDB stub and the standard GDB Remote Serial Protocol memory-read packet (`mADDR,LEN`). RenegadeAI deliberately does not expose memory/register write operations through this client.

`pret/pokeplatinum` is the structural source for the validated `SaveData`/`SavePageInfo` layout, save-table IDs, `PlayerSave`, `TrainerInfo`, `FieldOverworldState`, `Location`, `VarsFlags`, `MapObjectSave`, generated map headers, and generated story flag/variable names. Pokemon-Lua is used as an independent cross-reference for language-specific Platinum runtime SaveData pointer locations.

Runtime pointers are validated against Platinum structure invariants before RenegadeAI trusts them. Vision/OCR remains the verifier/fallback for unsupported or stale structured state.

## Autonomous Pokemon-agent references

- Continual Harness / PokeAgent — https://github.com/sethkarten/continual-harness
- NousResearch pokemon-agent — https://github.com/NousResearch/pokemon-agent
- Claude Plays Pokemon starter — https://github.com/davidhershey/ClaudePlaysPokemonStarter
- Extended LLM Pokemon scaffold — https://github.com/cicero225/llm_pokemon_scaffold
- GeminiPlaysPokemonLive — https://github.com/nichosta/GeminiPlaysPokemonLive
- PokemonRedExperiments — https://github.com/PWhiddy/PokemonRedExperiments
- Playing Pokemon Red via Deep Reinforcement Learning — https://arxiv.org/abs/2502.19920

These references informed architecture choices, not copied game assets. The recurring lesson is that long-horizon Pokemon completion works better as a hierarchy of structured state, objectives, pathfinding, memory, battle reasoning and recovery than as a single screenshot-to-button policy or pure reward maximizer.

See `AUTOPLAY_RESEARCH.md` and `STRUCTURED_MEMORY.md` for the detailed design takeaways.
