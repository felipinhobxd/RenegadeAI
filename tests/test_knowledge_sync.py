from renegade_ai.knowledge.sync import parse_pokemon_page

PAGE = """# Testmon

<div class="pokemon-hero">
<div class="pokemon-hero-dex-number">#123</div>
<span class="type-badge">Fire</span> <span class="type-badge">Dragon</span>
</div>

## :material-information: Basic Information

- [Levitate](../../pokedex/abilities/levitate.md)
- [Blaze](../../pokedex/abilities/blaze.md)

## :material-shield-half-full: Type Effectiveness

## :material-chart-bar: Base Stats

| **HP** | **78** | 1 | 2 |
| **Attack** | **84** | 1 | 2 |
| **Defense** | **78** | 1 | 2 |
| **Sp. Atk** | **110** | 1 | 2 |
| **Sp. Def** | **85** | 1 | 2 |
| **Speed** | **100** | 1 | 2 |

## :material-sword-cross: Moves

=== ":material-arrow-up-bold: Level-Up"

| Level | Move | Type | Category | Power | Accuracy | PP |
| 5 | [Ember](../../pokedex/moves/ember.md) | <span>Fire</span> | <span>Special</span> | 40 | 100 | 25 |

=== ":material-disc: TM/HM"

| Move | Type | Category | Power | Accuracy | PP |
| [Dragon Pulse](../../pokedex/moves/dragon-pulse.md) | <span>Dragon</span> | <span>Special</span> | 85 | 100 | 10 |
"""


def test_parse_pokemon_page_extracts_renegade_data():
    pokemon, moves = parse_pokemon_page("testmon", PAGE, "https://example.invalid/testmon.md")

    assert pokemon.dex == 123
    assert pokemon.name == "Testmon"
    assert pokemon.types == ("Fire", "Dragon")
    assert pokemon.abilities == ("Levitate", "Blaze")
    assert pokemon.special_attack == 110
    assert pokemon.speed == 100
    assert {entry.move for entry in pokemon.learnset} == {"ember", "dragon-pulse"}
    assert moves["ember"].power == 40
    assert moves["ember"].category == "Special"
    assert moves["dragon-pulse"].type == "Dragon"
