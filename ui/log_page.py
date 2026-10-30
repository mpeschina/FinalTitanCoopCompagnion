"""Log page: event log, undo, save and load, run statistics."""
from __future__ import annotations

import streamlit as st

from ui import session


def render() -> None:
    session.init()
    ss = st.session_state
    st.title("Log and save")
    state = session.game()
    if state is None:
        st.info("No game in progress.")
        up = st.file_uploader("Load a save file (JSON)", type="json", key="log_upload")
        if up is not None and st.button("Load"):
            err = session.load_json(up.getvalue())
            if err:
                st.error(err)
            else:
                session.go("arena")
        return

    c1, c2, c3 = st.columns([1, 1, 2])
    c1.button("Undo last event", on_click=session.undo, disabled=not ss.events, key="undo_log")
    c2.download_button("Save game", session.to_json(), file_name="final-titan-coop-save.json", mime="application/json")
    with c3.expander("Load a save file"):
        up = st.file_uploader("Save file (JSON)", type="json", key="log_upload2")
        if up is not None and st.button("Load", key="log_load"):
            err = session.load_json(up.getvalue())
            if err:
                st.error(err)
            else:
                st.rerun()

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Fight", state.fight_no)
    s2.metric("Enemies defeated", f"{len(state.defeated)} / {state.total}")
    s3.metric("Your Titans left", f"{state.player_titans_left} / {state.player_titans_total}")
    s4.metric("Events", len(ss.events))

    st.subheader("Log")
    for entry in reversed(state.log):
        prefix = "↳ " if entry.kind == "hint" else f"{entry.index}. "
        st.markdown(f"{prefix}{entry.text}")
