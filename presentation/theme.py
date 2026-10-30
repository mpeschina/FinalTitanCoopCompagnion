"""Layer 1: global comic theme, injected once per rerun."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parent / "assets"


@lru_cache(maxsize=2)
def _css(mtime: float) -> str:
    return (ASSETS / "comic.css").read_text(encoding="utf-8")


def inject_theme() -> None:
    # A style-only st.html goes to the event container, so it takes no space in the layout.
    st.html(f"<style>{_css((ASSETS / 'comic.css').stat().st_mtime)}</style>")
