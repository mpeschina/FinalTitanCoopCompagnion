"""Reusable view pieces outside the fight screen. The fight screen uses presentation.render."""
from __future__ import annotations

import html

import streamlit as st

from ui import images


def label(text: str) -> None:
    st.markdown(f'<p class="ft-label">{html.escape(text)}</p>', unsafe_allow_html=True)


TAKEN_ARROW = (
    '<div class="ft-taken-arrow" aria-hidden="true"><svg viewBox="0 0 100 120">'
    '<polygon points="33,8 67,8 67,60 90,60 50,112 10,60 33,60" transform="translate(7 7)" fill="#000" '
    'stroke="#000" stroke-width="7" stroke-linejoin="round"/>'
    '<polygon points="33,8 67,8 67,60 90,60 50,112 10,60 33,60" fill="#FFD400" '
    'stroke="#000" stroke-width="7" stroke-linejoin="round"/>'
    '<rect x="40" y="15" width="8" height="44" rx="3" fill="#FFF4A8"/>'
    '</svg></div>'
)


def card_image(path, width: int = 700, gray: bool = False, arrow: bool = False) -> None:
    data = images.thumb(path, width, gray)
    if data is None:
        st.caption("(no image)")
    else:
        st.image(data, width="stretch")
    if arrow:
        st.markdown(TAKEN_ARROW, unsafe_allow_html=True)
