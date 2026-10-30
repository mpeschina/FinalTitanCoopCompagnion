from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

ROOT = str(Path(__file__).resolve().parent.parent)


def run_page(page: str, pre=None, timeout=60):
    code = (
        "import sys\n"
        f"sys.path.insert(0, r'{ROOT}')\n"
        "from ui import session\n"
        "session.init()\n"
        f"from ui import {page}\n"
        f"{page}.render()\n"
    )
    at = AppTest.from_string(code, default_timeout=timeout)
    if pre:
        pre(at)
    return at.run()


def prepared(at):
    from finaltitan.catalog import load_catalog
    from finaltitan.setup import GameSetup, build_enemy, load_presets

    cat = load_catalog()
    s = GameSetup(players=1, difficulty="Easy", seed=2)
    s.player_titans = [t.id for t in cat.titans.values() if t.enemy_usable][:3]
    build_enemy(s, cat, load_presets())
    at.session_state["setup"] = s
    at.session_state["stage"] = "play"
    at.session_state["events"] = []
    at.session_state["version"] = 1


@pytest.mark.parametrize("page", ["setup_page", "draft_page", "log_page", "catalog_editor", "arena_page"])
def test_pages_render_without_exception(page):
    at = run_page(page)
    assert not at.exception, at.exception


def _click(at, prefix):
    btn = next(b for b in at.button if b.key and b.key.startswith(prefix))
    btn.click().run()
    assert not at.exception, at.exception


def test_setup_randomizes_seed_for_each_new_game_without_seed_controls():
    with patch("ui.setup_page.random.randint", side_effect=[123456, 654321]) as random_seed:
        at = run_page("setup_page")
        assert not at.exception, at.exception
        assert not any("seed" in item.label.lower() for item in at.number_input)
        assert not any("seed" in button.label.lower() for button in at.button)
        random_seed.assert_not_called()

        for expected_seed in [123456, 654321]:
            next(button for button in at.button if button.label == "Continue to draft").click().run()
            assert not at.exception, at.exception
            assert at.session_state["setup"].seed == expected_seed
            at.run()
            assert not at.exception, at.exception
            assert at.session_state["setup"].seed == expected_seed

        assert random_seed.call_count == 2
        random_seed.assert_called_with(1, 999_999)


def test_setup_guidance_survives_navigation_to_draft_and_back():
    code = (
        "import sys\n"
        f"sys.path.insert(0, r'{ROOT}')\n"
        "import streamlit as st\n"
        "from ui import session, setup_page, draft_page\n"
        "session.init()\n"
        "if st.session_state.stage == 'setup':\n"
        "    setup_page.render()\n"
        "else:\n"
        "    draft_page.render()\n"
    )
    at = AppTest.from_string(code, default_timeout=60).run()
    assert not at.exception, at.exception
    guidance = next(item for item in at.selectbox if item.label == "Guidance level")
    assert guidance.value == "Beginner"
    guidance.select("Expert").run()
    next(button for button in at.button if button.label == "Continue to draft").click().run()
    at.run()
    assert not at.exception, at.exception
    assert not any(item.label == "Guidance level" for item in at.selectbox)
    assert at.session_state["opt_level"] == "Expert"

    at.session_state["stage"] = "setup"
    at.run()
    assert not at.exception, at.exception
    assert next(item for item in at.selectbox if item.label == "Guidance level").value == "Expert"


@pytest.mark.parametrize("expansions", [["Base Set", "Advanced Set"], ["Base Set"], ["Advanced Set"]])
def test_setup_set_picker_controls_card_pool(expansions):
    from finaltitan.catalog import load_catalog
    from finaltitan.setup import _in_scope, build_enemy

    at = run_page("setup_page")
    assert not at.exception, at.exception
    assert at.multiselect[0].value == ["Base Set", "Advanced Set"]
    assert not any(toggle.label == "Include Advanced cards" for toggle in at.toggle)
    at.multiselect[0].set_value(expansions).run()
    assert not at.exception, at.exception
    next(button for button in at.button if button.label == "Continue to draft").click().run()
    assert not at.exception, at.exception
    setup = at.session_state["setup"]
    assert setup.expansions == expansions
    assert setup.advanced == ("Advanced Set" in expansions)
    catalog = load_catalog()
    for card in [*catalog.titans.values(), *catalog.upgrades.values()]:
        assert _in_scope(card, setup) == (card.expansion in expansions)
    build_enemy(setup, catalog, {})
    assert all(catalog.titans[card_id].expansion in expansions for card_id in setup.enemy_titans)
    assert all(catalog.upgrades[card_id].expansion in expansions for card_id in setup.enemy_upgrades)


@pytest.mark.parametrize("players", [1, 2, 3])
@pytest.mark.parametrize("picked", [0, 1, 3])
def test_draft_reserves_empty_slots(players, picked):
    from finaltitan.setup import GameSetup

    def pre(at):
        at.session_state["stage"] = "draft"
        at.session_state["setup"] = GameSetup(
            players=players, player_titans=["elite", "bast", "buzzkill"][:picked]
        )

    at = run_page("draft_page", pre)
    assert not at.exception, at.exception
    placeholders = [entry for entry in at.markdown if 'class="ft-draft-empty"' in entry.value]
    selected = [button for button in at.button if button.key and button.key.startswith("toggle_strip_")]
    assert len(placeholders) == players * 3 - picked
    assert len(placeholders) + len(selected) == players * 3


def test_draft_cards_toggle_once():
    def pre(at):
        at.session_state["stage"] = "draft"

    at = run_page("draft_page", pre)
    assert not at.exception, at.exception
    _click(at, "toggle_elite")
    assert at.session_state["setup"].player_titans == ["elite"]
    _click(at, "toggle_strip_elite")
    assert at.session_state["setup"].player_titans == []
    assert sum('class="ft-draft-empty"' in entry.value for entry in at.markdown) == 3
    _click(at, "toggle_elite")
    _click(at, "toggle_bast")
    _click(at, "toggle_buzzkill")
    assert at.session_state["setup"].player_titans == ["elite", "bast", "buzzkill"]
    assert not any(b.key == "toggle_chessmaster" for b in at.button)  # full: other cards are not clickable


def test_arena_full_flow_without_die_buttons():
    at = run_page("arena_page", prepared)
    assert not at.exception, at.exception
    _click(at, "beginner_setup_0")
    _click(at, "beginner_setup_1")
    _click(at, "primary_setup_0")
    _click(at, "beginner_fight_start_champion_0")
    _click(at, "beginner_fight_start_champion_1")
    _click(at, "beginner_fight_start_champion_2")
    _click(at, "primary_fight_start_champion_0")
    _click(at, "primary_enemy_turn_start")
    assert not any(b.key and b.key.startswith("face_") for b in at.button)
    _click(at, "primary_enemy_turn_0")
    _click(at, "primary_players_turn_0")
    _click(at, "dmg_q3")
    _click(at, "end_enemy_defeated")
    _click(at, "primary_cleanup_enemy_defeated")
    assert any(b.key and b.key.startswith("beginner_fight_start_challenger") for b in at.button)


@pytest.mark.parametrize("reason", ["enemy_defeated", "player_defeated", "both_defeated", "enemy_returned", "player_returned"])
def test_beginner_steps_work_in_the_next_fight(reason):
    at = run_page("arena_page", prepared)
    for key in ["beginner_setup_0", "beginner_setup_1", "primary_setup_0", "beginner_fight_start_champion_0",
                "beginner_fight_start_champion_1", "beginner_fight_start_champion_2", "primary_fight_start_champion_0",
                f"end_{reason}", f"primary_cleanup_{reason}"]:
        _click(at, key)
    for _ in range(4):
        step = next(b.key for b in at.button if b.key and b.key.startswith(("beginner_fight_start", "primary_fight_start")))
        _click(at, step)
        if step.startswith("primary_"):
            break
    assert at.session_state["_game"][1].phase == "combat"


@pytest.mark.parametrize("reason", ["enemy_defeated", "player_defeated", "both_defeated", "enemy_returned", "player_returned"])
def test_cleanup_has_no_checklist_or_confirmation_gate(reason):
    def pre(at):
        prepared(at)
        at.session_state["opt_level"] = "Expert"
        at.session_state["opt_confirm"] = True

    at = run_page("arena_page", pre)
    _click(at, "primary_setup_0")
    _click(at, "primary_fight_start_champion_0")
    at.session_state["opt_level"] = "Beginner"
    _click(at, f"end_{reason}")
    assert not at.checkbox
    primary = next(button for button in at.button if button.key == f"primary_cleanup_{reason}_0")
    assert not primary.disabled
    _click(at, f"primary_cleanup_{reason}")


def test_actions_queue_cues_and_undo_never_replays_them():
    def pre(at):
        prepared(at)
        at.session_state["opt_level"] = "Expert"

    at = run_page("arena_page", pre)
    _click(at, "primary_setup_0")
    assert [c["kind"] for c in at.session_state.fx_queue][:1] == ["title"]
    _click(at, "dmg_q2")
    queue = at.session_state.fx_queue
    assert "hit" in [c["kind"] for c in queue]
    assert all(c["id"].startswith("act-2-") for c in queue)
    assert at.session_state.fx_marks
    _click(at, "undo_top")
    assert at.session_state.fx_queue == [] and at.session_state.fx_marks == {}
    assert at.session_state.fx_cursor == len(at.session_state.events)


def test_beginner_setup_shows_one_confirmed_step_at_a_time():
    at = run_page("arena_page", prepared)
    assert not at.exception, at.exception
    assert any("Shuffle the physical Upgrade deck" in item.value for item in at.markdown)
    assert not any("Place your drafted Titans" in item.value for item in at.markdown)
    assert not any("Start of Game abilities" in item.value for item in at.markdown)

    _click(at, "beginner_setup_0")
    assert any("Place your drafted Titans" in item.value for item in at.markdown)
    assert not any("Shuffle the physical Upgrade deck" in item.value for item in at.markdown)
    assert not any("Start of Game abilities" in item.value for item in at.markdown)

    _click(at, "beginner_setup_1")
    assert any("Start of Game abilities" in item.value for item in at.markdown)
    _click(at, "primary_setup_0")
    assert at.session_state.version == 2

    assert any("is the enemy Champion" in item.value for item in at.markdown)
    assert not any("face down" in item.value for item in at.markdown)
    assert not any(b.key and b.key.startswith("primary_fight_start") for b in at.button)
    _click(at, "beginner_fight_start_champion_0")
    assert any("face down" in item.value for item in at.markdown)
    assert not any("is the enemy Champion" in item.value for item in at.markdown)


def test_fight_menu_changes_guidance_live_without_changing_game():
    def pre(at):
        prepared(at)
        at.session_state["opt_level"] = "Expert"

    at = run_page("arena_page", pre)
    _click(at, "primary_setup_0")
    version = at.session_state["version"]
    event_count = len(at.session_state["events"])
    guidance = next(item for item in at.selectbox if item.label == "Guidance level")
    assert guidance.value == "Expert"
    guidance.select("Beginner").run()
    assert not at.exception, at.exception
    assert at.session_state["opt_level"] == "Beginner"
    assert any(button.key == "beginner_fight_start_champion_0" for button in at.button)

    next(item for item in at.selectbox if item.label == "Guidance level").select("Expert").run()
    assert not at.exception, at.exception
    assert at.session_state["opt_level"] == "Expert"
    assert any(button.key == "primary_fight_start_champion_0" for button in at.button)
    assert not any(button.key and button.key.startswith("beginner_") for button in at.button)
    assert at.session_state["version"] == version
    assert len(at.session_state["events"]) == event_count


def test_fight_menu_fx_settings_are_kept_in_session():
    def pre(at):
        prepared(at)
        at.session_state["opt_level"] = "Expert"

    at = run_page("arena_page", pre)
    _click(at, "primary_setup_0")
    next(item for item in at.selectbox if item.label == "FX intensity").select("Low").run()
    assert not at.exception, at.exception
    assert at.session_state["fx_intensity"] == "Low"
    next(item for item in at.toggle if item.label == "Sound").set_value(True).run()
    assert at.session_state["fx_sound"] is True
    assert next(item for item in at.selectbox if item.label == "FX intensity").value == "Low"
    assert not next(item for item in at.slider if item.label == "Volume").disabled


def test_expert_setup_keeps_existing_start_button():
    def pre(at):
        prepared(at)
        at.session_state["opt_level"] = "Expert"

    at = run_page("arena_page", pre)
    assert not at.exception, at.exception
    assert any(button.key == "primary_setup_0" for button in at.button)
    assert not any(button.key and button.key.startswith("beginner_setup") for button in at.button)
