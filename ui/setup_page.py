"""Setup page: player count, difficulty, filters, and save loading."""
from __future__ import annotations

import random

import streamlit as st

from finaltitan.guide import LEVELS
from finaltitan.setup import DIFFICULTIES, MAX_PLAYERS, GameSetup
from ui import session


def render() -> None:
    session.init()
    ss = st.session_state
    cat = session.catalog()
    presets = session.presets()
    st.title("Final Titan Co-op Companion")
    st.write("The app plays and shows the enemy team. You play your own Titans with the physical game.")
    if ss.stage == "play":
        st.info("A game is in progress. Continuing to the draft replaces it.")

    left, right = st.columns(2)
    with left:
        players = st.segmented_control("Number of players", list(range(1, MAX_PLAYERS + 1)), default=ss.setup.players, key="setup_count") or 1
        labels = {None: "None (random decks)", **{k: v["name"] for k, v in presets.items()}}
        options = list(labels)
        preset = st.selectbox("Challenge preset", options, format_func=labels.get, index=options.index(ss.setup.preset) if ss.setup.preset in options else 0)
        difficulty = st.select_slider("Difficulty", DIFFICULTIES, value=ss.setup.difficulty, disabled=preset is not None)
    with right:
        all_exp = cat.expansions()
        default_expansions = [name for name in ("Base Set", "Advanced Set") if name in all_exp]
        expansions = st.multiselect("Expansions in the pool", all_exp, default=ss.setup.expansions or default_expansions)
        advanced = "Advanced Set" in expansions

    setup = GameSetup(players=players, difficulty=difficulty, expansions=expansions, advanced=advanced, preset=preset)
    if preset is None:
        st.caption(f"The enemy team has {setup.enemy_count()} Titans. You will mark {setup.player_titan_count()} Titans taken by the players.")
    else:
        st.caption("The preset fixes the enemy Titans and Upgrades.")

    ss._setup_guidance = session.settings().level
    st.selectbox("Guidance level", LEVELS, key="_setup_guidance",
                 on_change=lambda: ss.update(opt_level=ss._setup_guidance, beginner_progress=None))

    if st.button("Continue to draft", type="primary", disabled=not expansions):
        setup.seed = random.randint(1, 999_999)
        ss.setup = setup
        ss.events = []
        ss.version += 1
        ss.stage = "draft"
        session.go("draft")

    with st.expander("Load a saved game"):
        up = st.file_uploader("Save file (JSON)", type="json")
        if up is not None and st.button("Load"):
            err = session.load_json(up.getvalue())
            if err:
                st.error(err)
            else:
                session.go("arena")
