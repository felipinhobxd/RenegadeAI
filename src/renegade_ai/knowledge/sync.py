from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from renegade_ai.knowledge.dex import DEFAULT_KNOWLEDGE_DIR
from renegade_ai.knowledge.models import LearnMove, MoveData, PokemonData
from renegade_ai.strategy.profiles import build_all_profiles


WIKI_REPOSITORY = "zhenga8533/renegade-platinum-wiki"
# Pin knowledge parsing to a known wiki revision so a future wiki layout change
# cannot silently corrupt the agent's battle data.
WIKI_COMMIT = "7e8956b8f138deaece1ed9c3ee7be22dc1437438"
WIKI_DIRECTORY = "docs/pokedex/pokemon"
WIKI_API = (
    "https://api.github.com/repos/"
    f"{WIKI_REPOSITORY}/contents/{WIKI_DIRECTORY}?ref={WIKI_COMMIT}"
)
WIKI_RAW = f"https://raw.githubusercontent.com/{WIKI_REPOSITORY}/{WIKI_COMMIT}/{WIKI_DIRECTORY}"
SPRITE_RAW = (
    "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/versions/"
    "generation-iv/platinum"
)

_USER_AGENT = "RenegadeAI/0.2 knowledge-sync"
_TYPE_RE = re.compile(r'class="type-badge"[^>]*>([^<]+)</span>', re.IGNORECASE)
_LINK_MOVE_RE = re.compile(r"\[([^\]]+)\]\([^)]*/moves/([^/)]+)\.md\)")
_ABILITY_RE = re.compile(r"\[([^\]]+)\]\([^)]*/abilities/([^/)]+)\.md\)")
_DEX_RE = re.compile(r'pokemon-hero-dex-number">#(\d+)', re.IGNORECASE)
_STAT_RE = {
    "hp": re.compile(r"\| \*\*HP\*\* \| \*\*(\d+)\*\*"),
    "attack": re.compile(r"\| \*\*Attack\*\* \| \*\*(\d+)\*\*"),
    "defense": re.compile(r"\| \*\*Defense\*\* \| \*\*(\d+)\*\*"),
    "special_attack": re.compile(r"\| \*\*Sp\. Atk\*\* \| \*\*(\d+)\*\*"),
    "special_defense": re.compile(r"\| \*\*Sp\. Def\*\* \| \*\*(\d+)\*\*"),
    "speed": re.compile(r"\| \*\*Speed\*\* \| \*\*(\d+)\*\*"),
}


def _request_bytes(url: str, timeout: float = 30.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS sources
        return response.read()


def _request_text(url: str, timeout: float = 30.0) -> str:
    return _request_bytes(url, timeout).decode("utf-8")


def _plain_number(value: str) -> int | None:
    value = value.strip().replace("—", "").replace("-", "")
    if not value:
        return None
    match = re.search(r"\d+", value)
    return None if match is None else int(match.group())


def _span_text(cell: str) -> str:
    matches = re.findall(r">([^<>]+)</span>", cell)
    return matches[-1].strip() if matches else re.sub(r"<[^>]+>", "", cell).strip()


def _method_from_heading(line: str) -> str | None:
    lower = line.lower()
    if "level-up" in lower:
        return "level-up"
    if "tm/hm" in lower or "machine" in lower:
        return "machine"
    if "tutor" in lower:
        return "tutor"
    if "egg" in lower:
        return "egg"
    return None


def _parse_move_row(line: str, method: str) -> tuple[LearnMove, MoveData] | None:
    if "pokedex/moves/" not in line or not line.lstrip().startswith("|"):
        return None
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if method == "level-up":
        if len(cells) < 7 or not cells[0].isdigit():
            return None
        level = int(cells[0])
        offset = 1
    else:
        if len(cells) < 6:
            return None
        level = None
        offset = 0

    move_match = _LINK_MOVE_RE.search(cells[offset])
    if move_match is None:
        return None
    name, slug = move_match.groups()
    move_type = _span_text(cells[offset + 1])
    category = _span_text(cells[offset + 2])
    power = _plain_number(cells[offset + 3])
    accuracy = _plain_number(cells[offset + 4])
    pp = _plain_number(cells[offset + 5])
    return (
        LearnMove(move=slug, method=method, level=level),
        MoveData(
            slug=slug,
            name=name,
            type=move_type,
            category=category,
            power=power,
            accuracy=accuracy,
            pp=pp,
        ),
    )


def parse_pokemon_page(slug: str, text: str, source_url: str) -> tuple[PokemonData, dict[str, MoveData]]:
    title_match = re.search(r"^# (.+)$", text, flags=re.MULTILINE)
    dex_match = _DEX_RE.search(text)
    if title_match is None or dex_match is None:
        raise ValueError(f"Could not parse identity from {slug}")
    name = title_match.group(1).strip()
    dex_number = int(dex_match.group(1))

    hero = text.split("## :material-information:", 1)[0]
    types: list[str] = []
    for value in _TYPE_RE.findall(hero):
        normalized = value.strip()
        if normalized not in types:
            types.append(normalized)
        if len(types) == 2:
            break

    basic = text.split("## :material-information:", 1)[-1]
    basic = basic.split("## :material-shield-half-full:", 1)[0]
    abilities: list[str] = []
    for ability_name, _ability_slug in _ABILITY_RE.findall(basic):
        if ability_name not in abilities:
            abilities.append(ability_name)

    stats: dict[str, int] = {}
    for key, pattern in _STAT_RE.items():
        match = pattern.search(text)
        if match is None:
            raise ValueError(f"Missing {key} for {slug}")
        stats[key] = int(match.group(1))

    learnset: list[LearnMove] = []
    moves: dict[str, MoveData] = {}
    inside_moves = False
    method: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            inside_moves = "Moves" in line and "material-sword-cross" in line
            if not inside_moves:
                method = None
            continue
        if not inside_moves:
            continue
        if line.startswith("=== "):
            method = _method_from_heading(line)
            continue
        if method is None:
            continue
        parsed = _parse_move_row(line, method)
        if parsed is None:
            continue
        learned, move = parsed
        learnset.append(learned)
        moves.setdefault(move.slug, move)

    return (
        PokemonData(
            dex=dex_number,
            slug=slug,
            name=name,
            types=tuple(types),
            abilities=tuple(abilities),
            hp=stats["hp"],
            attack=stats["attack"],
            defense=stats["defense"],
            special_attack=stats["special_attack"],
            special_defense=stats["special_defense"],
            speed=stats["speed"],
            learnset=tuple(learnset),
            source_url=source_url,
        ),
        moves,
    )


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _wiki_entries() -> list[dict[str, Any]]:
    raw = json.loads(_request_text(WIKI_API))
    if not isinstance(raw, list):
        raise RuntimeError("Unexpected GitHub response while listing Renegade Platinum Pokemon")
    return [
        item
        for item in raw
        if isinstance(item, dict)
        and str(item.get("name", "")).endswith(".md")
        and item.get("type") == "file"
    ]


def sync_knowledge(
    root: str | Path = DEFAULT_KNOWLEDGE_DIR,
    *,
    workers: int = 12,
) -> dict[str, int | str]:
    root = Path(root)
    entries = _wiki_entries()
    pokemon: dict[str, PokemonData] = {}
    moves: dict[str, MoveData] = {}

    def download(entry: dict[str, Any]):
        filename = str(entry["name"])
        slug = filename[:-3]
        raw_url = f"{WIKI_RAW}/{filename}"
        text = _request_text(raw_url)
        return parse_pokemon_page(slug, text, raw_url)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [executor.submit(download, entry) for entry in entries]
        for future in as_completed(futures):
            record, record_moves = future.result()
            if 1 <= record.dex <= 493:
                pokemon[record.slug] = record
                for slug, move in record_moves.items():
                    moves.setdefault(slug, move)

    national_numbers = {record.dex for record in pokemon.values() if 1 <= record.dex <= 493}
    if len(national_numbers) != 493:
        missing = sorted(set(range(1, 494)) - national_numbers)
        raise RuntimeError(
            f"Knowledge sync was incomplete: {len(national_numbers)}/493 National Dex IDs; "
            f"missing first IDs: {missing[:12]}"
        )

    strategies = build_all_profiles(pokemon, moves)
    _atomic_json(root / "pokemon.json", {slug: value.to_dict() for slug, value in pokemon.items()})
    _atomic_json(root / "moves.json", {slug: value.to_dict() for slug, value in moves.items()})
    _atomic_json(root / "strategies.json", {slug: value.to_dict() for slug, value in strategies.items()})
    _atomic_json(
        root / "manifest.json",
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "wiki_repository": WIKI_REPOSITORY,
            "wiki_commit": WIKI_COMMIT,
            "pokemon_records": len(pokemon),
            "national_dex_species": len(national_numbers),
            "moves": len(moves),
            "strategies": len(strategies),
        },
    )
    return {
        "pokemon_records": len(pokemon),
        "national_dex_species": len(national_numbers),
        "moves": len(moves),
        "strategies": len(strategies),
        "wiki_commit": WIKI_COMMIT,
    }


def _download_sprite(url: str, destination: Path) -> bool:
    if destination.exists() and destination.stat().st_size > 0:
        return False
    try:
        payload = _request_bytes(url)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_bytes(payload)
    temporary.replace(destination)
    return True


def sync_platinum_sprites(
    root: str | Path = Path("data/sprites/platinum"),
    *,
    workers: int = 24,
) -> dict[str, int]:
    """Cache front/back Platinum sprites for National Dex 1-493.

    Sprites are downloaded locally from PokeAPI's sprite repository and are not
    committed into RenegadeAI. They are used as an optional visual-recognition
    fallback when OCR is uncertain.
    """
    root = Path(root)
    jobs: list[tuple[str, Path]] = []
    for dex in range(1, 494):
        jobs.append((f"{SPRITE_RAW}/{dex}.png", root / "front" / f"{dex}.png"))
        jobs.append((f"{SPRITE_RAW}/back/{dex}.png", root / "back" / f"{dex}.png"))

    downloaded = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [executor.submit(_download_sprite, url, path) for url, path in jobs]
        for future in as_completed(futures):
            downloaded += int(future.result())
    return {"requested": len(jobs), "downloaded": downloaded}
