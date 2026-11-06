"""Setup page: player count, difficulty, filters, and save loading."""
from __future__ import annotations

import random

import streamlit as st

from finaltitan.guide import LEVELS
from finaltitan.setup import DIFFICULTIES, MAX_PLAYERS, GameSetup
from ui import components, session


def render() -> None:
    session.init()
    ss = st.session_state
    cat = session.catalog()
    presets = session.presets()
    tr = session.translator()
    if ss.stage == "play":
        session.back_button("back_setup")
    head, flags = st.columns([4, 1], vertical_alignment="center")
    head.title(tr("setup.title"))
    with flags:
        components.language_picker("setup")
    st.write(tr("setup.intro"))
    if ss.stage == "play":
        st.info(tr("setup.in_progress"))

    left, right = st.columns(2)
    with left:
        players = st.segmented_control(tr("setup.players"), list(range(1, MAX_PLAYERS + 1)), default=ss.setup.players, key="setup_count") or 1
        labels = {"": tr("setup.preset_none"), **{k: v["name"] for k, v in presets.items()}}
        options = list(labels)
        # Seeded from the setup instead of passing defaults, so a language switch can re-assert them (session.set_lang).
        ss.setdefault("setup_preset", ss.setup.preset if ss.setup.preset in options else "")
        ss.setdefault("setup_difficulty", ss.get("_setup_difficulty", ss.setup.difficulty))
        preset = st.selectbox(tr("setup.preset"), options, format_func=labels.get, key="setup_preset") or None
        if preset is None:
            difficulty = st.select_slider(tr("setup.difficulty"), DIFFICULTIES, format_func=lambda v: tr(f"opt.{v}"),
                                          key="setup_difficulty")
        else:  # the preset fixes the enemy decks, so the slider would carry no information: it is not shown
            difficulty = ss.setup_difficulty
        ss._setup_difficulty = difficulty  # keeps the choice across the runs in which the slider is not rendered
    with right:
        all_exp = cat.expansions()
        default_expansions = [name for name in ("Base Set", "Advanced Set") if name in all_exp]
        expansions = st.multiselect(tr("setup.expansions"), all_exp, default=ss.setup.expansions or default_expansions, key="setup_expansions")
        advanced = "Advanced Set" in expansions

    setup = GameSetup(players=players, difficulty=difficulty, expansions=expansions, advanced=advanced, preset=preset)
    if preset is None:
        st.caption(tr("setup.counts", enemy=setup.enemy_count(), mine=setup.player_titan_count()))
    else:
        st.caption(tr("setup.preset_fixed"))

    ss._setup_guidance = session.settings().level
    with st.container(key="setup_guidance"):
        pick, hint = st.columns(2, vertical_alignment="center")
        with pick:
            st.selectbox(tr("guidance.label"), LEVELS, key="_setup_guidance", format_func=lambda v: tr(f"opt.{v}"),
                         on_change=lambda: ss.update(opt_level=ss._setup_guidance, beginner_progress=None))
        if ss._setup_guidance == "Expert":  # the hint has done its job once Beginner is picked
            with hint:
                components.speech_bubble(tr("guidance.hint_title"), tr("guidance.hint"))

    if st.button(tr("setup.continue"), type="primary", disabled=not expansions):
        setup.seed = random.randint(1, 999_999)
        ss.setup = setup
        ss.events = []
        ss.version += 1
        ss.stage = "draft"
        session.go("draft")

    with st.expander(tr("setup.load_saved")):
        up = st.file_uploader(tr("common.save_file"), type="json", key="setup_upload")
        if up is not None and st.button(tr("common.load")):
            err = session.load_json(up.getvalue())
            if err:
                st.error(err)
            else:
                session.go("arena")
