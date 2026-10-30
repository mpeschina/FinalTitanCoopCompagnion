"""Image helpers: cached thumbnails and generated card backs."""
from __future__ import annotations

import io
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw, ImageEnhance, ImageFont


@st.cache_data(show_spinner=False)
def _thumb(path: str, width: int, mtime: float, gray: bool) -> bytes:
    with Image.open(path) as im:
        im = im.convert("RGB")
        height = round(im.height * width / im.width)
        im = im.resize((width, height), Image.LANCZOS)
    if gray:
        im = ImageEnhance.Brightness(im.convert("L").convert("RGB")).enhance(0.55)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def thumb(path: Path | None, width: int, gray: bool = False) -> bytes | None:
    if path is None or not Path(path).exists():
        return None
    return _thumb(str(path), width, Path(path).stat().st_mtime, gray)


@st.cache_data(show_spinner=False)
def upgrade_back(width: int = 300) -> bytes:
    """The Upgrade card back is not part of the assets, so a neutral one is drawn."""
    height = round(width * 1039 / 744)
    im = Image.new("RGB", (width, height), "#1b2a41")
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((8, 8, width - 8, height - 8), radius=18, outline="#c9a227", width=4)
    font = ImageFont.load_default(size=max(14, width // 9))
    d.text((width / 2, height / 2), "UPGRADE", fill="#c9a227", font=font, anchor="mm")
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def show(path: Path | None, width: int, gray: bool = False) -> None:
    data = thumb(path, width, gray)
    if data is None:
        st.caption("(no image)")
    else:
        st.image(data, width=width)
