from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

ROOT = str(Path(__file__).resolve().parent.parent)


def prepared_beginner(at):
    prepared(at)
    at.session_state["opt_level"] = "Beginner"


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
    assert guidance.value == "Expert"
    guidance.select("Beginner").run()
    next(button for button in at.button if button.label == "Continue to draft").click().run()
    at.run()
    assert not at.exception, at.exception
    assert not any(item.label == "Guidance level" for item in at.selectbox)
    assert at.session_state["opt_level"] == "Beginner"

    at.session_state["stage"] = "setup"
    at.run()
    assert not at.exception, at.exception
    assert next(item for item in at.selectbox if item.label == "Guidance level").value == "Beginner"


def test_setup_defaults_to_expert_with_hint_bubble_until_beginner_is_picked():
    at = run_page("setup_page")
    assert not at.exception, at.exception
    assert next(item for item in at.selectbox if item.label == "Guidance level").value == "Expert"
    assert any("ft-bubble" in entry.value for entry in at.markdown)
    next(item for item in at.selectbox if item.label == "Guidance level").select("Beginner").run()
    assert not any("ft-bubble" in entry.value for entry in at.markdown)


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


@pytest.mark.parametrize("level, rules", [("Beginner", True), ("Expert", False)])
def test_draft_explains_rules_only_to_beginners(level, rules):
    def pre(at):
        at.session_state["stage"] = "draft"
        at.session_state["opt_level"] = level

    at = run_page("draft_page", pre)
    assert not at.exception, at.exception
    texts = [entry.value for entry in at.markdown]
    assert any("youngest player" in text for text in texts) == rules
    assert any("Max Life" in text and "Speed" in text for text in texts) == rules


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
    at = run_page("arena_page", prepared_beginner)
    assert not at.exception, at.exception
    _click(at, "beginner_setup_0")
    _click(at, "beginner_setup_1")
    _click(at, "primary_setup_0")
    _click(at, "beginner_fight_start_champion_0")
    _click(at, "beginner_fight_start_champion_1")
    _click(at, "beginner_fight_start_champion_2")
    _click(at, "primary_fight_start_champion_0")
    assert not any(b.key and b.key.startswith("face_") for b in at.button)
    _click(at, "primary_enemy_turn_0")
    _click(at, "primary_players_turn_0")
    _click(at, "dmg_q3")
    _click(at, "end_enemy_defeated")
    _click(at, "primary_cleanup_enemy_defeated")
    assert any(b.key and b.key.startswith("beginner_fight_start_challenger") for b in at.button)


@pytest.mark.parametrize("reason", ["enemy_defeated", "player_defeated", "both_defeated", "enemy_returned", "player_returned"])
def test_beginner_steps_work_in_the_next_fight(reason):
    at = run_page("arena_page", prepared_beginner)
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
    at = run_page("arena_page", prepared_beginner)
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


def test_catalog_menu_entry_only_in_debug_mode():
    at = run_page("arena_page", prepared)
    _click(at, "primary_setup_0")
    assert any(b.key == "menu_log" for b in at.button)
    assert not any(b.key == "menu_catalog" for b in at.button)

    with patch("ui.session.debug", return_value=True):
        at = run_page("arena_page", prepared)
        _click(at, "primary_setup_0")
    assert any(b.key == "menu_catalog" for b in at.button)


def test_fight_menu_has_no_setup_or_draft_and_new_game_abandons_the_game():
    at = run_page("arena_page", prepared)
    _click(at, "primary_setup_0")
    assert not any(b.key in ("menu_setup", "menu_draft") for b in at.button)
    _click(at, "menu_new")
    assert at.session_state["stage"] == "setup"
    assert at.session_state["events"] == []


def test_catalog_editor_is_locked_outside_debug_mode():
    at = run_page("catalog_editor")
    assert not at.exception, at.exception
    assert any(b.key == "back_catalog" for b in at.button)
    assert not at.segmented_control


def test_log_page_has_back_button_during_a_game():
    at = run_page("log_page", prepared)
    assert not at.exception, at.exception
    assert any(b.key == "back_log" for b in at.button)
    assert not any(b.key == "back_log" for b in run_page("log_page").button)


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


def test_language_defaults_to_english_and_flags_switch_setup_to_german():
    at = run_page("setup_page")
    assert at.session_state["lang"] == "en"
    assert at.title[0].value == "Final Titan Co-op Companion"
    _click(at, "setup_langbtn_de")
    assert at.session_state["lang"] == "de"
    assert at.title[0].value == "Final Titan Koop-Begleiter"
    assert at.query_params["lang"] in ("de", ["de"])  # AppTest returns a list on 1.60, a string on 1.61+
    assert any(b.label == "Weiter zum Draft" for b in at.button)


def test_language_comes_from_the_url_when_chosen_before():
    def pre(at):
        at.query_params["lang"] = "de"

    at = run_page("setup_page", pre)
    assert at.session_state["lang"] == "de"
    assert next(item for item in at.selectbox if item.label == "Anleitungsstufe").value == "Expert"


def test_setup_choices_survive_a_language_switch():
    at = run_page("setup_page")
    next(item for item in at.select_slider if item.label == "Difficulty").set_value("Hard").run()
    _click(at, "setup_langbtn_de")
    assert next(item for item in at.select_slider if item.label == "Schwierigkeit").value == "Hard"
    next(item for item in at.select_slider if item.label == "Schwierigkeit").set_value("Insane").run()
    _click(at, "setup_langbtn_en")
    assert next(item for item in at.select_slider if item.label == "Difficulty").value == "Insane"
    assert next(item for item in at.selectbox if item.label == "Challenge preset").value == ""


def test_fight_menu_switches_language_without_changing_game():
    def pre(at):
        prepared(at)
        at.session_state["opt_level"] = "Expert"

    at = run_page("arena_page", pre)
    _click(at, "primary_setup_0")
    version = at.session_state["version"]
    events = list(at.session_state["events"])
    queue = at.session_state["fx_queue"]
    _click(at, "menu_langbtn_de")
    assert at.session_state["lang"] == "de"
    assert any(b.label == "Gegner beginnt" for b in at.button)
    assert any(item.label == "Anleitungsstufe" for item in at.selectbox)
    assert at.session_state["version"] == version
    assert at.session_state["events"] == events
    assert at.session_state["fx_queue"] == queue
    _click(at, "menu_langbtn_en")
    assert any(b.label == "Enemy starts" for b in at.button)


# ------------------------------------------------------------------ enemy dice

def enemy_turn_page(*extra, level="Expert"):
    from finaltitan import events as ev
    from finaltitan.events import act

    def pre(at):
        prepared(at)
        at.session_state["opt_level"] = level
        at.session_state["events"] = [act(ev.BEGIN_GAME), act(ev.SET_STARTER, side="enemy"), *extra]
        at.session_state["version"] = 2

    return run_page("arena_page", pre)


def _markdown(at):
    return " ".join(m.value for m in at.markdown)


def test_roll_button_rolls_a_die_and_fills_the_tracker():
    at = enemy_turn_page()
    assert not at.exception, at.exception
    assert "Action 1 of 1" in _markdown(at)
    _click(at, "ft_enemy_roll")
    rolls = [e for e in at.session_state["events"] if e.kind == "roll"]
    assert len(rolls) == 1 and len(rolls[0].args["faces"]) == 1 and rolls[0].args["token"] == "none"
    assert rolls[0].args["faces"][0] in ("blue", "green", "yellow", "red", "charge", "miss")
    assert [c["kind"] for c in at.session_state.fx_queue][0] == "roll"
    assert "All Actions rolled" in _markdown(at)
    assert any(b.key == "ft_enemy_roll_done" for b in at.button)  # gray, but still usable
    _click(at, "ft_enemy_roll_done")
    assert len([e for e in at.session_state["events"] if e.kind == "roll"]) == 2
    _click(at, "undo_top")
    assert len([e for e in at.session_state["events"] if e.kind == "roll"]) == 1
    assert at.session_state.fx_queue == []


def test_roll_never_touches_the_game_state_beyond_the_log():
    at = enemy_turn_page()
    before = at.session_state["_game"][1].arena
    life, charged = before.life, before.charged
    for _ in range(3):
        _click(at, next(b.key for b in at.button if b.key and b.key.startswith("ft_enemy_roll")))
    arena = at.session_state["_game"][1].arena
    assert (arena.life, arena.charged) == (life, charged)


def test_blessed_enemy_rolls_two_dice_and_the_players_pick_one():
    from finaltitan import events as ev
    from finaltitan.events import act

    at = enemy_turn_page()
    arena = at.session_state["_game"][1].arena.card_id
    at.session_state["events"] = [*at.session_state["events"], act(ev.TOKEN, target=arena, token="blessed", delta=1)]
    at.session_state["version"] += 1
    at.run()
    _click(at, "ft_enemy_roll")
    roll = next(e for e in at.session_state["events"] if e.kind == "roll")
    assert len(roll.args["faces"]) == 2 and roll.args["token"] == "blessed"
    state = at.session_state["_game"][1]
    if state.turn_rolls[-1].doubles:
        assert any(b.key == "ft_remove_token" for b in at.button)
        _click(at, "ft_remove_token")
        assert at.session_state["_game"][1].arena.statuses.blessed_cursed == "none"
    else:
        picks = [b for b in at.button if b.key and b.key.startswith("ft_pick_")]
        assert len(picks) == 2
        assert at.session_state["_game"][1].turn_rolls[-1].pending
        _click(at, picks[1].key)
        assert at.session_state["_game"][1].turn_rolls[-1].pick == 1
        assert not any(b.key and b.key.startswith("ft_pick_") for b in at.button)
        assert [c["kind"] for c in at.session_state.fx_queue][0] == "roll_pick"


def test_roll_button_and_tracker_speak_german():
    def pre(at):
        prepared(at)
        at.session_state["opt_level"] = "Expert"
        at.session_state["lang"] = "de"
        from finaltitan import events as ev
        from finaltitan.events import act
        at.session_state["events"] = [act(ev.BEGIN_GAME), act(ev.SET_STARTER, side="enemy")]
        at.session_state["version"] = 2

    at = run_page("arena_page", pre)
    assert not at.exception, at.exception
    assert any(b.label == "Würfeln" for b in at.button)
    assert "Aktion 1 von 1" in _markdown(at)


def test_expert_mode_hides_the_result_hint_but_beginner_keeps_it():
    from finaltitan import events as ev
    from finaltitan.events import act

    roll = act(ev.ROLL, faces=["red"], token="none")
    expert = enemy_turn_page(roll, level="Expert")
    assert "resolve the glowing icon" not in _markdown(expert)
    beginner = enemy_turn_page(roll, level="Beginner")
    assert "resolve the glowing icon" in _markdown(beginner)
