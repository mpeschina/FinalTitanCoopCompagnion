# Final Titan Co-op Companion

A Streamlit web app that plays the **enemy team** in the Solo & Co-op mode of the card game *Final Titan*.

The app is an enemy display: one shared screen at the table shows the current enemy Titan, its Life and tokens, the active enemy Upgrades, and the enemies still to come. Players keep handling their own Titans, tokens and cards with the physical game. All dice, including the enemy's, are rolled physically. The app never rolls dice and never asks for a die result.

## Features

- **Setup**: 1 to 3 players, difficulty from Easy to Insane, or a fixed challenge preset. Expansion and Advanced filters and an optional seed.
- **Draft**: mark the Titans the players drafted so the enemy can't get them. You can filter by Power, Speed and name.
- **Enemy decks**: a seeded random enemy Titan deck and a hidden enemy Upgrade hand, sized by the difficulty table. Legendary Upgrades attach automatically.
- **Guided play**: an instruction panel always says who acts next (enemy, players or everyone) and what to do, with "Why?" explanations and hints. Choose Beginner or Expert guidance.
- **Enemy rules engine**: queue order, Champion/Challenger roles, Upgrade reveals, Charge and Ultimate, Status tokens, start-of-turn Poison and Fire damage, the damage order (Armor, Dodge, Minion), fight clean-up, and victory and defeat detection.
- **Undo** for every change. The engine is an event-sourced pure reducer.
- **Save and load** the game as a JSON file, plus a full game log.
- **Catalog editor** to check and edit card metadata next to each card image.
- **Comic fighting-game presentation**: a themed HUD with animated reveals, cinematics, optional sound and enemy taunts. All of it can be adjusted in the sidebar, including a reduced-motion mode.

The app never reads or applies card text. Players read the card images and enter the results with the controls.

## Requirements

- Python 3.10+
- The packages in [requirements.txt](requirements.txt): `streamlit>=1.60`, `pillow`, `pyyaml`, `pytest`

## Installation

```
python -m pip install -r requirements.txt
```

## Running the app

```
python -m streamlit run app.py
```

Streamlit opens the app in your browser, by default at http://localhost:8501. It is designed for a 1920 × 1080 window and also works at 1366 × 768 with a little scrolling.

### How a game goes

1. **Setup**: choose the number of players and the difficulty or a preset.
2. **Draft**: draft Titans physically, then click the 3 × players Titans you took.
3. **Enemy**: follow the instruction panel. Each fight goes like this:
   - The enemy Titan enters as Champion or Challenger.
   - You tell the app who starts.
   - On the enemy's turn, you roll for the enemy and resolve the result on its card.
   - On your turn, you enter the damage and tokens you deal to the enemy.
   - When the fight ends, the app runs the clean-up and reveals the next Upgrade.
4. **Log and save**: review the log, or save and load the game.

The sidebar holds the effect settings (FX intensity, cinematics, animation speed, sound, taunts, K.O. style, reduced motion) and a **New game** button.

## Running the tests

```
python -m pytest
```

## Card data

Card images live in `assets/`:

```
assets/
  Final Titan Card Database.csv   # card database (not in the repository, see below)
  titans/<id>.jpg                 # Titans the enemy may use
  titans/noCoop/<id>.jpg          # Titans the enemy can't use (players can still draft them)
  titans/finalTitanCardBackside.jpg
  upgrades/<id>.jpg               # one file per physical copy (powerPotion2.jpg, …)
```

A card is part of the game only if it has an image. The generated catalog in `data/titans.csv` and `data/upgrades.csv` is committed, so the app runs without the card database.

The card database itself isn't included in the repository. You only need it to regenerate the catalog: place it at `assets/Final Titan Card Database.csv`. After you add or rename images, rebuild the catalog and the static card images:

```
# English database rows + images -> data/titans.csv, data/upgrades.csv
python -m finaltitan.build_catalog

# Card images and thumbnails served from static/cards/
python -m presentation.build_static
```

`build_catalog` reports any images it couldn't match to the database. Fix those with the aliases in [finaltitan/build_catalog.py](finaltitan/build_catalog.py) or in the in-app **Catalog editor**.

Challenge presets (fixed enemy decks per player count) are defined in [data/presets.yaml](data/presets.yaml). All guide texts are in [data/guide.yaml](data/guide.yaml).

## Project structure

```
app.py                  # entry point: page navigation and sidebar settings
finaltitan/             # rules engine, no UI code
  state.py              #   game state dataclasses (enemy side only)
  events.py             #   action types
  engine.py             #   pure reducer: (state, action) -> state
  combat.py             #   damage order, start-of-turn damage
  setup.py              #   difficulty table, presets, deck building
  guide.py              #   guide(state, settings) -> instructions
  catalog.py            #   load, validate and save card metadata
  build_catalog.py      #   database CSV + images -> data/*.csv
ui/                     # Streamlit pages and session handling
presentation/           # comic theme, HUD templates, FX and animations
data/                   # card catalog, presets, guide texts
static/                 # generated card images and fonts (served by Streamlit)
design/                 # rules and design documents
tests/                  # pytest suite
```

## Design documents

- [design/rules.md](design/rules.md): the general Final Titan rules
- [design/final-titan-coop-rules.md](design/final-titan-coop-rules.md): Solo & Co-op mode rules
- [design/webapp-design.md](design/webapp-design.md): app scope, game flow, engine and layout
- [design/presentation-design.md](design/presentation-design.md): the comic presentation layer

## License

The source code is licensed under the [MIT License](LICENSE). If you use it, keep the copyright notice and credit the original author.

The card images, card artwork, card texts and card data (`assets/`, `static/cards/`, `data/titans.csv`, `data/upgrades.csv`) are **copyright Nerdlab Games** and are **not** covered by the MIT License. See [LICENSE](LICENSE) for details.

## Disclaimer

This is an unofficial fan-made companion. It is not affiliated with or endorsed by Nerdlab Games. *Final Titan*, its card artwork and its rules belong to Nerdlab Games. You need a copy of the physical game to play.
