"""Final Titan Co-op Companion: entry point and navigation."""
import streamlit as st

from presentation import fx
from presentation.theme import inject_theme
from ui import arena_page, catalog_editor, draft_page, log_page, session, setup_page

st.set_page_config(page_title="Final Titan Co-op", page_icon="🗿", layout="wide", initial_sidebar_state="collapsed")
session.init()
inject_theme()

pages = {
    "setup": st.Page(setup_page.render, title="Setup", icon="⚙", url_path="setup", default=True),
    "draft": st.Page(draft_page.render, title="Draft", icon="🃏", url_path="draft"),
    "arena": st.Page(arena_page.render, title="Enemy", icon="⚔", url_path="arena"),
    "log": st.Page(log_page.render, title="Log and save", icon="📜", url_path="log"),
    "catalog": st.Page(catalog_editor.render, title="Catalog editor", icon="🗂", url_path="catalog"),
}
st.session_state.pages = pages

with st.sidebar:
    st.header("Effects")
    st.selectbox("FX intensity", fx.INTENSITIES, index=2, key="fx_intensity", help="Low: no particles and no shake.")
    st.selectbox("Cinematics", fx.CINEMATICS, index=1, key="fx_cinematics")
    st.select_slider("Animation speed", fx.SPEEDS, value=1.0, key="fx_speed", format_func=lambda v: f"{v:g}×")
    sound = st.toggle("Sound", value=False, key="fx_sound")
    st.slider("Volume", 0.0, 1.0, 0.6, 0.05, key="fx_volume", disabled=not sound)
    st.toggle("Enemy taunts", value=True, key="fx_taunts")
    st.selectbox("K.O. style", fx.KO_STYLE_OPTIONS, key="fx_ko_style")
    st.toggle("Idle motion and mouse tilt", value=True, key="fx_idle")
    st.selectbox("Reduced motion", fx.REDUCED_MOTION, key="fx_reduced", help="System follows the operating system setting.")
    st.divider()
    st.button("New game", on_click=session.new_game, key="new_side", width="stretch")

st.navigation(list(pages.values()), position="top").run()
