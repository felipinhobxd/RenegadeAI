# Sources

RenegadeAI keeps downloaded/generated knowledge out of Git and records the public projects used as technical references.

## Renegade Platinum data

The knowledge sync downloads public Renegade Platinum documentation at runtime and pins the external revision used to generate local data. Generated Pokemon/move/strategy JSON and sprite caches live under `data/` and are ignored by Git.

The repository does **not** include a Renegade Platinum ROM, a Pokemon Platinum ROM, BIOS/firmware, save files, savestates or extracted copyrighted game assets.

## Pokemon / emulator engineering references

- melonDS — https://github.com/melonDS-emu/melonDS
- Pokemon Platinum decompilation — https://github.com/pret/pokeplatinum
- Platinum Lua/QoL memory tooling — https://github.com/hzla/Pokemon-Lua

These are useful for the planned read-only structured-state backend: map ID, player coordinates, facing, collisions/warps/objects and objective state where reliable symbols/structures can be identified.

## Autonomous Pokemon-agent references

- Continual Harness / PokeAgent — https://github.com/sethkarten/continual-harness
- NousResearch pokemon-agent — https://github.com/NousResearch/pokemon-agent
- Claude Plays Pokemon starter — https://github.com/davidhershey/ClaudePlaysPokemonStarter
- Extended LLM Pokemon scaffold — https://github.com/cicero225/llm_pokemon_scaffold
- GeminiPlaysPokemonLive — https://github.com/nichosta/GeminiPlaysPokemonLive
- PokemonRedExperiments — https://github.com/PWhiddy/PokemonRedExperiments
- Playing Pokemon Red via Deep Reinforcement Learning — https://arxiv.org/abs/2502.19920

These references informed architecture choices, not copied game assets. The recurring lesson is that long-horizon Pokemon completion works better as a hierarchy of structured state, objectives, pathfinding, memory, battle reasoning and recovery than as a single screenshot-to-button policy or pure reward maximizer.

See `AUTOPLAY_RESEARCH.md` for the detailed design takeaways.
