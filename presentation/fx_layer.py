"""Layer 3: the FX overlay. One same-origin iframe per page; its script installs the engine into the
parent page once (it survives reruns there) and hands it the cues of the latest action."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import streamlit as st

from presentation.fx import FxSettings

ASSETS = Path(__file__).resolve().parent / "assets"
ENGINE_FILES = ("fx.js", "motion.js", "destroy.js", "cinematics.js")

BOOT = """<script>
(function () {
  var payload = __PAYLOAD__;
  var P = null;
  try { P = window.parent; if (!P || P === window || !P.document.body) P = null; } catch (e) { P = null; }
  if (!P) { return; }
  if (!P.__ftFx || P.__ftFx.version !== payload.engine) {
    var s = P.document.createElement('script');
    s.textContent = __ENGINE__;
    P.document.head.appendChild(s);
  }
  if (P.__ftFx && P.__ftFx.receive) { P.__ftFx.receive(payload); }
})();
</script>"""


def _json(obj: Any) -> str:
    # Safe inside a <script> element: no closing tags or HTML comments can appear in the literal.
    return json.dumps(obj).replace("</", "<\\/").replace("<!--", "<\\!--")


@lru_cache(maxsize=2)
def _engine(mtimes: tuple[float, ...]) -> tuple[str, str]:
    src = "\n".join((ASSETS / name).read_text(encoding="utf-8") for name in ENGINE_FILES)
    version = hashlib.sha1(src.encode("utf-8")).hexdigest()[:12]
    return version, "(function () {\n" + src.replace("__VERSION__", version) + "\n})();"


def engine() -> tuple[str, str]:
    """(version, code) of the overlay engine; the version changes whenever a source file changes."""
    return _engine(tuple((ASSETS / name).stat().st_mtime for name in ENGINE_FILES))


def payload_html(cues: list[dict[str, Any]], settings: FxSettings, assets: dict[str, str | None]) -> str:
    version, code = engine()
    payload = {"engine": version, "cues": cues, "settings": settings.to_dict(), "assets": assets}
    return BOOT.replace("__ENGINE__", _json(code)).replace("__PAYLOAD__", _json(payload))


def fx_layer(cues: list[dict[str, Any]], settings: FxSettings, assets: dict[str, str | None]) -> None:
    with st.container(key="ft_fxhost"):
        st.iframe(payload_html(cues, settings, assets), height="content")
