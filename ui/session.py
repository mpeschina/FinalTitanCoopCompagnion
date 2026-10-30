"""Streamlit session helpers: catalog cache, event log, derived game state."""
from __future__ import annotations

import json
from typing import Any

import streamlit as st

from finaltitan.catalog import Catalog, load_catalog
from finaltitan.engine import apply, initial_state, reduce
from finaltitan.events import Action, act
from finaltitan.guide import GuidanceSettings
from finaltitan.setup import GameSetup, load_presets
from finaltitan.state import GameState
from presentation import fx

SAVE_VERSION = 3


@st.cache_resource
def catalog() -> Catalog:
    return load_catalog()


@st.cache_resource
def presets() -> dict[str, dict[str, Any]]:
    return load_presets()


def init() -> None:
    ss = st.session_state
    ss.setdefault("setup", GameSetup())
    ss.setdefault("events", [])
    ss.setdefault("version", 0)
    ss.setdefault("stage", "setup")  # setup | draft | play
    ss.setdefault("reveal_marker", 0)
    ss.setdefault("beginner_progress", None)  # ((step, event_count), confirmed lines)
    ss.setdefault("pages", {})
    ss.setdefault("fx_queue", [])  # cue dicts of the latest action
    ss.setdefault("fx_marks", {})  # Layer 2 marks of the latest action
    ss.setdefault("fx_cursor", len(ss.events))  # number of actions already turned into cues


def settings() -> GuidanceSettings:
    ss = st.session_state
    return GuidanceSettings(level=ss.get("opt_level", "Beginner"))


def fx_settings() -> fx.FxSettings:
    ss = st.session_state
    d = fx.FxSettings()
    return fx.FxSettings(
        intensity=ss.get("fx_intensity", d.intensity), cinematics=ss.get("fx_cinematics", d.cinematics),
        speed=float(ss.get("fx_speed", d.speed)), sound=bool(ss.get("fx_sound", d.sound)),
        volume=float(ss.get("fx_volume", d.volume)), taunts=bool(ss.get("fx_taunts", d.taunts)),
        ko_style=ss.get("fx_ko_style", d.ko_style), idle=bool(ss.get("fx_idle", d.idle)),
        reduced_motion=ss.get("fx_reduced", d.reduced_motion),
    )


def reset_fx() -> None:
    """History never replays as animation: skip cue generation for everything up to now."""
    ss = st.session_state
    ss.fx_queue = []
    ss.fx_marks = {}
    ss.fx_cursor = len(ss.events)


def game() -> GameState | None:
    ss = st.session_state
    if ss.stage != "play":
        return None
    cached = ss.get("_game")
    if cached and cached[0] == ss.version:
        return cached[1]
    state = reduce(initial_state(ss.setup, catalog()), ss.events)
    ss["_game"] = (ss.version, state)
    return state


def dispatch(kind: str, **args: Any) -> None:
    ss = st.session_state
    before = game()
    action = act(kind, **args)
    ss.events.append(action)
    ss.version += 1
    if before is None or ss.get("fx_cursor", 0) != len(ss.events) - 1:
        reset_fx()
        return
    after = apply(before, action)
    ss["_game"] = (ss.version, after)
    summary = None
    if after.phase in ("victory", "defeat") and before.phase != after.phase:
        summary = fx.game_summary(initial_state(ss.setup, catalog()), ss.events)
    cues = fx.cues_for(action, before, after, prefix=f"act-{after.event_count}-v{ss.version}", summary=summary,
                       difficulty=ss.setup.difficulty, ko_setting=fx_settings().ko_style)
    ss.fx_queue = [c.to_dict() for c in cues]
    ss.fx_marks = fx.marks_for(cues, after.event_count)
    ss.fx_cursor = len(ss.events)


def undo() -> None:
    ss = st.session_state
    if ss.events:
        ss.events.pop()
        ss.version += 1
        ss.reveal_marker = len(ss.events)
        reset_fx()


def go(page: str) -> None:
    pg = st.session_state.pages.get(page)
    if pg is not None:
        st.switch_page(pg)


def start_game() -> None:
    ss = st.session_state
    ss.events = []
    ss.version += 1
    ss.stage = "play"
    ss.reveal_marker = 0
    ss.beginner_progress = None
    reset_fx()


def new_game() -> None:
    ss = st.session_state
    ss.setup = GameSetup()
    ss.events = []
    ss.version += 1
    ss.stage = "setup"
    ss.reveal_marker = 0
    ss.beginner_progress = None
    reset_fx()


def to_json() -> str:
    ss = st.session_state
    return json.dumps(
        {"version": SAVE_VERSION, "setup": ss.setup.to_dict(), "events": [a.to_dict() for a in ss.events]}, indent=1
    )


def load_json(raw: bytes) -> str | None:
    """Loads a save file. Returns an error message, or None on success."""
    try:
        data = json.loads(raw)
        if data.get("version") != SAVE_VERSION:
            return "This save file was made by an older version of the app."
        setup = GameSetup.from_dict(data["setup"])
        events = [Action.from_dict(e) for e in data["events"]]
        cat = catalog()
        for cid in setup.enemy_titans + list(setup.player_titans):
            if cid not in cat.titans:
                return f"Unknown Titan '{cid}' in save file."
        state = reduce(initial_state(setup, cat), events)
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
        return f"Invalid save file: {exc}"
    ss = st.session_state
    ss.setup, ss.events, ss.stage = setup, events, "play"
    ss.version += 1
    ss.reveal_marker = state.event_count
    reset_fx()
    return None
