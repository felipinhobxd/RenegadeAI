# External data sources

RenegadeAI does not ship a ROM, BIOS/firmware, save files or an extracted game asset pack.

## Renegade Platinum game knowledge

The runtime `knowledge-sync` command builds its local structured battle knowledge from the community Renegade Platinum wiki repository:

- Repository: `zhenga8533/renegade-platinum-wiki`
- Pinned revision: `7e8956b8f138deaece1ed9c3ee7be22dc1437438`
- Parsed area: `docs/pokedex/pokemon/*.md`

The revision is deliberately pinned. RenegadeAI validates that the generated dataset contains all National Dex IDs 1 through 493 before replacing the local knowledge files.

The parser extracts the Renegade-specific values exposed by those pages, including current typing, abilities, base stats, and Level-Up / TM-HM / Tutor / Egg move data. Generated strategy profiles are RenegadeAI output; they are not copied strategy text from the wiki.

Generated files live under `data/knowledge/` and are ignored by Git.

## Optional sprite cache

`renegade-ai knowledge-sync --sprites` optionally caches Generation IV Platinum front/back sprites from the PokeAPI sprites repository:

- Repository: `PokeAPI/sprites`
- Path family: `sprites/pokemon/versions/generation-iv/platinum/`

The sprite cache is stored under `data/sprites/platinum/`, is ignored by Git, and is intended as a visual-recognition fallback. Battle HUD text recognition is preferred when it is reliable because the game itself displays the species name.

## Source policy

External data is downloaded on the user's machine. Generated caches are reproducible and are not committed to this repository. RenegadeAI's own planner, type engine, strategy generation, perception code and learning code live in this repository.
