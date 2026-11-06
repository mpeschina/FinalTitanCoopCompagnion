"""Streamlit session helpers: catalog cache, event log, derived game state."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import streamlit as st

from finaltitan import dice, events as ev
from finaltitan.catalog import Catalog, load_catalog
from finaltitan.engine import apply, initial_state, reduce
from finaltitan.events import Action, act
from finaltitan.guide import GuidanceSettings
from finaltitan.i18n import LANGS, Msg, pick_lang, render, t
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
    if "lang" not in ss:  # a manual choice is kept in the URL; otherwise the browser locale decides
        ss.lang = pick_lang(st.query_params.get("lang") or st.context.locale)


def lang() -> str:
    return st.session_state.get("lang") or pick_lang(None)


# Widgets whose option labels are translated. Streamlit matches their values by label, so a language switch
# re-asserts their values from Python (read here with the old labels) instead of the frontend's old label.
TRANSLATED_WIDGETS = ("setup_difficulty", "setup_preset", "ed_kind", "tok_kind")


def set_lang(code: str) -> None:
    ss = st.session_state
    if code not in LANGS:
        return
    for key in TRANSLATED_WIDGETS:
        if key in ss:
            ss[key] = ss[key]
    ss.lang = code
    st.query_params["lang"] = code


def tr(key: str, **params: Any) -> str:
    return t(key, lang(), **params)


def translator() -> Callable[..., str]:
    """tr bound to the current language; safe for format_func, which Streamlit may call outside the run."""
    current = lang()
    return lambda key, **params: t(key, current, **params)


def text(m: Msg | str) -> str:
    return render(m, lang())


def settings() -> GuidanceSettings:
    ss = st.session_state
    return GuidanceSettings(level=ss.get("opt_level", "Expert"), lang=lang())


def fx_settings() -> fx.FxSettings:
    ss = st.session_state
    d = fx.FxSettings()
    return fx.FxSettings(
        intensity=ss.get("fx_intensity", d.intensity), cinematics=ss.get("fx_cinematics", d.cinematics),
        speed=float(ss.get("fx_speed", d.speed)), sound=bool(ss.get("fx_sound", d.sound)),
        volume=float(ss.get("fx_volume", d.volume)), taunts=bool(ss.get("fx_taunts", d.taunts)),
        ko_style=ss.get("fx_ko_style", d.ko_style), idle=bool(ss.get("fx_idle", d.idle)),
        reduced_motion=ss.get("fx_reduced_motion", d.reduced_motion), lang=lang(),
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
                       difficulty=tr(f"opt.{ss.setup.difficulty}"), ko_setting=fx_settings().ko_style, lang=lang())
    ss.fx_queue = [c.to_dict() for c in cues]
    ss.fx_marks = fx.marks_for(cues, after.event_count)
    ss.fx_cursor = len(ss.events)


def roll_enemy() -> None:
    """The Roll button. The die is drawn here and stored in the event, so replay and undo stay exact."""
    state = game()
    if state is None or state.arena is None:
        return
    token = state.arena.statuses.blessed_cursed
    dispatch(ev.ROLL, faces=dice.roll(1 if token == "none" else 2), token=token)


def undo() -> None:
    ss = st.session_state
    if ss.events:
        ss.events.pop()
        ss.version += 1
        ss.reveal_marker = len(ss.events)
        reset_fx()


def debug() -> bool:
    """DEBUG = true in .streamlit/secrets.toml unlocks developer pages such as the catalog editor."""
    try:
        return bool(st.secrets.get("DEBUG", False))
    except FileNotFoundError:  # no secrets file at all
        return False


def go(page: str) -> None:
    pg = st.session_state.pages.get(page)
    if pg is not None:
        st.switch_page(pg)


def back_button(key: str) -> None:
    """The way back from a screen opened in the fight menu; there is no page bar."""
    st.button(tr("common.back"), key=key, on_click=go, args=("arena",))


def start_game() -> None:
    ss = st.session_state
    ss.events = []
    ss.version += 1
    ss.stage = "play"
    ss.reveal_marker = 0
    ss.beginner_progress = None
    reset_fx()


def rematch() -> None:
    """Rematch after a defeat: the same setup, draft and enemy decks (the seed is kept), played from the start."""
    start_game()
    go("arena")


def new_game() -> None:
    """Abandons the current game and opens the Setup screen."""
    ss = st.session_state
    ss.setup = GameSetup()
    ss.events = []
    ss.version += 1
    ss.stage = "setup"
    ss.reveal_marker = 0
    ss.beginner_progress = None
    reset_fx()
    go("setup")


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
            return tr("save.old_version")
        setup = GameSetup.from_dict(data["setup"])
        events = [Action.from_dict(e) for e in data["events"]]
        cat = catalog()
        for cid in setup.enemy_titans + list(setup.player_titans):
            if cid not in cat.titans:
                return tr("save.unknown_titan", id=cid)
        state = reduce(initial_state(setup, cat), events)
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
        return tr("save.invalid", err=exc)
    ss = st.session_state
    ss.setup, ss.events, ss.stage = setup, events, "play"
    ss.version += 1
    ss.reveal_marker = state.event_count
    reset_fx()
    return None
