"""Draft page: click the Titans the players took, so the enemy cannot get them."""
from __future__ import annotations

import streamlit as st

from finaltitan.setup import build_enemy, reserved_titans
from ui import components, session

GRID_COLS = 6
PAGE_SIZE = 24


def _toggle(card_id: str) -> None:
    taken = st.session_state.setup.player_titans
    if card_id in taken:
        taken.remove(card_id)
    elif len(taken) < st.session_state.setup.player_titan_count():
        taken.append(card_id)


def _start() -> None:
    ss = st.session_state
    try:
        ss.warnings = build_enemy(ss.setup, session.catalog(), session.presets())
    except ValueError as exc:
        ss.draft_error = str(exc)
        return
    ss.draft_error = None
    session.start_game()
    ss.go_arena = True


def _card(card, width: int, key: str, taken: bool, blocked: bool = False, note: str = "") -> None:
    """A borderless card image with its name above; clicking it toggles the card."""
    st.caption(f"**{card.name}** · {card.max_life} / {card.speed}{note}")
    with st.container(key=f"card_{key}"):
        components.card_image(card.image, width, gray=taken or blocked, arrow=taken)
        if not blocked:
            st.button(card.name, key=f"toggle_{key}", on_click=_toggle, args=(card.id,))


def render() -> None:
    session.init()
    ss = st.session_state
    if ss.stage == "setup":
        st.info("Configure the game on the Setup page first.")
        st.button("Go to Setup", on_click=session.go, args=("setup",))
        return
    if ss.pop("go_arena", False):
        session.go("arena")
    setup, cat = ss.setup, session.catalog()
    need = setup.player_titan_count()
    taken = list(dict.fromkeys(setup.player_titans))  # each Titan only once
    setup.player_titans = taken
    st.title("Draft")
    st.write(f"Draft your Titans on the table as usual, then click the **{need}** Titans you took, so the enemy never gets them. Find each one by the Power (max Life) and Speed printed on the card. Click a marked card again to unmark it.")

    with st.container(key="draft_header"):
        head, action = st.columns([5, 2], vertical_alignment="center")
        head.markdown(f"**Taken by players: {len(taken)} / {need}**")
        if len(taken) == need:
            if ss.get("draft_error"):
                st.error(ss.draft_error)
            action.button("Build enemy decks and start", type="primary", on_click=_start, width="stretch")
    with st.container(key="draft_slots"):
        for index, col in enumerate(st.columns(max(need, GRID_COLS))[:need]):
            with col:
                if index < len(taken):
                    cid = taken[index]
                    _card(cat.titans[cid], 200, f"strip_{cid}", taken=False)
                else:
                    st.caption("\u00a0")
                    st.markdown(
                        f'<div class="ft-draft-empty" role="img" aria-label="Empty Titan spot {index + 1}">'
                        '<span>Empty spot</span></div>',
                        unsafe_allow_html=True,
                    )

    reserved = reserved_titans(setup, cat, session.presets())
    f1, f2, f3 = st.columns(3)
    power = f1.number_input("Power (max Life)", min_value=0, value=None, step=1, placeholder="any")
    speed = f2.number_input("Speed", min_value=0, value=None, step=1, placeholder="any")
    name = f3.text_input("Name contains", placeholder="optional")
    pool = [
        t for t in cat.titans.values()
        if (not setup.expansions or t.expansion in setup.expansions)
        and (power is None or t.max_life == power)
        and (speed is None or t.speed == speed)
        and (not name or name.lower() in t.name.lower())
    ]
    pool.sort(key=lambda t: (t.max_life, t.speed, t.name))
    st.caption(f"{len(pool)} matches")
    shown = pool if len(pool) <= PAGE_SIZE or st.checkbox(f"Show all {len(pool)}") else pool[:PAGE_SIZE]

    for start in range(0, len(shown), GRID_COLS):
        for col, t in zip(st.columns(GRID_COLS), shown[start:start + GRID_COLS]):
            with col:
                _card(t, 320, t.id, taken=t.id in taken, blocked=t.id in reserved or (len(taken) >= need and t.id not in taken),
                      note=" · reserved for the enemy" if t.id in reserved else "")
