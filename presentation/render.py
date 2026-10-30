"""HTML for the fight screen: cards, life bar, token badges, HUD pieces, caption badge, ticker.

Every dynamic text value goes through html.escape, numbers are cast to int, and image paths are built only
from catalog ids that pass a whitelist. No Streamlit imports.
"""
from __future__ import annotations

import html
import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path
from string import Template
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from finaltitan.catalog import Catalog
from finaltitan.state import EnemyTitan, GameState

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
URL = "app/static"
TEMPLATES = Path(__file__).resolve().parent / "templates"
SIZES = {"full": 760, "thumb": 300}
KINDS = ("titans", "upgrades")
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
Marks = dict[str, tuple[int, Any]]

TOKEN_INFO = {
    "armor": ("&#128737;", "Armor", "Reduces each instance of damage by 1 per token."),
    "poison": ("&#9760;", "Poison", "Damage equal to the tokens at the start of its turn; ignores Armor, Dodge, Minion."),
    "fire": ("&#128293;", "Fire", "Damage equal to the tokens at the start of its turn, then +1 Fire; removed after the fight."),
    "power": ("&#128170;", "Power", "Each token adds 1 to all damage this Titan deals."),
    "dodge": ("&#128168;", "Dodge", "The next instance of damage is prevented and the token is lost."),
    "minion": ("&#129485;", "Minion", "Prevents one instance of damage that would defeat this Titan."),
    "action": ("&#10133;", "Action", "One extra Action on each of its turns."),
}
ACTOR_ICONS = {"players": "&#128101;", "all": "&#127922;"}


@lru_cache(maxsize=None)
def template(name: str) -> Template:
    # Lines are stripped and joined, so Markdown never sees indented code blocks or blank lines.
    text = (TEMPLATES / f"{name}.html").read_text(encoding="utf-8")
    return Template("".join(line.strip() for line in text.splitlines()))


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _fx(marks: Marks | None, key: str) -> tuple[str, Any]:
    """('act-N', value before) when the action N changed this target, else ('static', None)."""
    mark = (marks or {}).get(key)
    return (f"act-{int(mark[0])}", mark[1]) if mark else ("static", None)


# ----------------------------------------------------------------- static images

def _write_webp(im: Image.Image, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".webp", dir=dest.parent)
    os.close(fd)
    im.save(tmp, "WEBP", quality=82, method=4)
    os.replace(tmp, dest)


def ensure_image(src: Path, dest: Path, width: int) -> bool:
    if dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime:
        return True
    if not src.exists():
        return False
    with Image.open(src) as im:
        im = im.convert("RGB")
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    _write_webp(im, dest)
    return True


def _rel(kind: str, card_id: str, size: str) -> str:
    return f"cards/{kind}/{card_id}.webp" if size == "full" else f"cards/thumbs/{kind}/{card_id}.webp"


def card_src(cat: Catalog, kind: str, card_id: str, size: str = "full") -> str | None:
    if kind not in KINDS or size not in SIZES or not _ID.match(card_id or ""):
        return None
    card = (cat.titans if kind == "titans" else cat.upgrades).get(card_id)
    if card is None or card.image is None:
        return None
    rel = _rel(kind, card_id, size)
    if not ensure_image(Path(card.image), STATIC / rel, SIZES[size]):
        return None
    return f"{URL}/{rel}"


def _draw_upgrade_back(dest: Path, width: int = 300) -> None:
    height = round(width * 1039 / 744)
    im = Image.new("RGB", (width, height), "#16161C")
    d = ImageDraw.Draw(im)
    for y in range(0, height, 10):
        for x in range((y // 10) % 2 * 5, width, 10):
            d.ellipse((x, y, x + 2, y + 2), fill="#2a1d05")
    d.rounded_rectangle((8, 8, width - 8, height - 8), radius=18, outline="#FFD400", width=5)
    font = ImageFont.load_default(size=max(14, width // 8))
    d.text((width / 2, height / 2), "UPGRADE", fill="#FFD400", font=font, anchor="mm", stroke_width=3, stroke_fill="#000")
    _write_webp(im, dest)


def back_src(cat: Catalog, kind: str) -> str | None:
    if kind == "titans":
        if cat.titan_back is None or not ensure_image(Path(cat.titan_back), STATIC / "cards/backs/titan.webp", SIZES["thumb"]):
            return None
        return f"{URL}/cards/backs/titan.webp"
    dest = STATIC / "cards/backs/upgrade.webp"
    if not dest.exists():
        _draw_upgrade_back(dest)
    return f"{URL}/cards/backs/upgrade.webp"


def build_all(cat: Catalog) -> int:
    """Generates every card image and thumbnail once. Returns the number of cards processed."""
    count = 0
    for kind, pool in (("titans", cat.titans), ("upgrades", cat.upgrades)):
        for cid in pool:
            for size in SIZES:
                count += card_src(cat, kind, cid, size) is not None
    back_src(cat, "titans")
    back_src(cat, "upgrades")
    return count


# ------------------------------------------------------------------- cards

def card_html(cat: Catalog, kind: str, card_id: str, *, cls: str = "", marks: Marks | None = None,
              overlay: str = "", size: str = "full", name: str | None = None, fx_prefix: str = "card") -> str:
    src = card_src(cat, kind, card_id, size)
    pool = cat.titans if kind == "titans" else cat.upgrades
    card = pool.get(card_id)
    alt = name or (card.name if card else card_id)
    fx_id = f"{fx_prefix}-{card_id}"
    fx, value = _fx(marks, fx_id)
    classes = [cls]
    if value == "arrive":
        classes.append("ft-arriving l2-arrive")
    elif isinstance(value, str):
        classes.append(f"l2-{value}")
    if src is None:
        return f'<div class="ft-card ft-missing {esc(cls)}" data-fx-id="{esc(fx_id)}">{esc(alt)}</div>'
    zoom = card_src(cat, kind, card_id, "full") if size != "full" else src
    return template("card").substitute(
        cls=esc(" ".join(c for c in classes if c)), fx_id=esc(fx_id), fx=fx, src=esc(src),
        alt=esc(alt), zoom=esc(zoom or src), overlay=overlay,
    )


def stack_html(cat: Catalog, kind: str, count: int, zone: str, label: str) -> str:
    """A face-down stack (deck or enemy Upgrade hand) that is also a spawn zone for card motion."""
    src = back_src(cat, kind)
    layers = min(max(int(count), 0), 4)
    imgs = "".join(
        f'<img class="ft-stack-card" src="{esc(src)}" alt="" style="--i:{i}">' for i in range(layers)
    ) if src else ""
    empty = " empty" if count <= 0 else ""
    return (f'<div class="ft-stack{empty}" data-fx-zone="{esc(zone)}"><div class="ft-stack-cards">{imgs}</div>'
            f'<span class="ft-stack-label">{esc(label)} <b>{int(count)}</b></span></div>')


def badges_html(t: EnemyTitan, marks: Marks | None = None) -> str:
    st_ = t.statuses
    parts = []
    for key, (icon, name, tip) in TOKEN_INFO.items():
        n = getattr(st_, key)
        if n <= 0:
            continue
        fx, before = _fx(marks, f"badge-{t.card_id}-{key}")
        pop = " pop" if fx != "static" else ""
        tick = f" &middot; -{int(n)}/turn" if key in ("poison", "fire") else ""
        parts.append(
            f'<span class="ft-tok tok-{key}{pop}" data-fx="{fx}" data-fx-id="badge-{esc(t.card_id)}-{key}" '
            f'title="{esc(name)}: {esc(tip)}"><i>{icon}</i><b>{int(n)}</b><em>{esc(name)}{tick}</em></span>'
        )
    if st_.blessed_cursed != "none":
        word = st_.blessed_cursed
        fx, _ = _fx(marks, f"badge-{t.card_id}-{word}")
        label = "Blessed &ndash; ENEMY picks" if word == "blessed" else "Cursed &ndash; YOU pick"
        tip = "Rolls two dice; the enemy picks." if word == "blessed" else "Rolls two dice; the players pick."
        parts.append(
            f'<span class="ft-tok tok-{word}{" pop" if fx != "static" else ""}" data-fx="{fx}" '
            f'data-fx-id="badge-{esc(t.card_id)}-{word}" title="{tip}"><i>&#127922;&#127922;</i><em>{label}</em></span>'
        )
    if t.ultimate_form:
        parts.append('<span class="ft-tok tok-uform" title="The Ultimate Form ability is active."><i>&#9733;</i><em>Ultimate Form</em></span>')
    if t.team_power:
        parts.append('<span class="ft-tok tok-team" title="Active for the whole enemy team, even from the bench."><i>&#9873;</i><em>Team Power</em></span>')
    return f'<div class="ft-badges">{"".join(parts)}</div>' if parts else ""


def arena_overlay(t: EnemyTitan, marks: Marks | None = None) -> str:
    fx, _ = _fx(marks, f"charge-{t.card_id}")
    chg = (f'<span class="ft-chg-ind{" on" if t.charged else ""}" data-fx="{fx}" '
           f'data-fx-target="charge-{esc(t.card_id)}">&#9889;</span>')
    return badges_html(t, marks) + chg


def arena_classes(t: EnemyTitan) -> str:
    cls = ["arena", "enemy"]
    if t.life is not None and t.max_life and t.life / t.max_life <= 0.3:
        cls.append("low")
    if t.charged:
        cls.append("charged")
    if t.ultimate_form:
        cls.append("uform")
    return " ".join(cls)


def life_bar_html(t: EnemyTitan, marks: Marks | None = None) -> str:
    life, max_life = int(t.life or 0), max(int(t.max_life), 1)
    to = max(0.0, min(1.0, life / max_life))
    fx, before = _fx(marks, f"life-{t.card_id}")
    frm = float(before) if isinstance(before, (int, float)) else to
    cls = ("anim " if fx != "static" else "") + ("up " if frm < to else "") + ("low" if to <= 0.3 else "mid" if to <= 0.6 else "high")
    return template("lifebar").substitute(
        cls=cls, fx=fx, **{"from": f"{frm:.3f}"}, to=f"{to:.3f}", pips=min(max_life, 40), life=life, max=max_life
    )


# --------------------------------------------------------------------- HUD

def pips_html(on: int, total: int, kind: str) -> str:
    on, total = max(int(on), 0), max(int(total), 0)
    return "".join(f'<i class="pip {kind}{" on" if i < on else ""}"></i>' for i in range(total))


def hud_players_html(state: GameState) -> str:
    pips = pips_html(state.player_titans_left, state.player_titans_total, "titan")
    count = f'<span class="ft-count">{int(state.player_titans_left)}/{int(state.player_titans_total)}</span>'
    return template("hud_players").substitute(
        titans_left=f'<span class="ft-pips" data-fx-target="titans-left">{pips}</span>{count}'
    )


def hud_center_html(state: GameState) -> str:
    turn, turn_cls = "", ""
    if state.phase == "combat":
        turn, turn_cls = ("ENEMY TURN", "enemy") if state.active_side == "enemy" else ("YOUR TURN", "players")
    elif state.phase in ("victory", "defeat"):
        turn, turn_cls = state.phase.upper(), state.phase
    elif state.phase == "fight_start":
        turn, turn_cls = "FIGHT START", "neutral"
    elif state.phase == "cleanup":
        turn, turn_cls = "CLEAN-UP", "neutral"
    done = len(state.defeated)
    return template("hud_center").substitute(
        fight=int(state.fight_no), turn=esc(turn), turn_cls=turn_cls,
        defeated=pips_html(done, state.total, "ko") + f'<span class="ft-count">{done}/{int(state.total)}</span>',
    )


def hud_enemy_html(state: GameState) -> str:
    t = state.arena
    if t is None:
        return template("hud_enemy").substitute(role="", name="&mdash;", stats="")
    armor = f"{t.base_armor}+{t.statuses.armor}" if t.statuses.armor else str(int(t.base_armor))
    spd = f'{int(t.speed)}{"*" if t.speed_override is not None else ""}'
    stats = (f'<span class="ft-stat" title="Armor"><i>ARM</i>{esc(armor)}</span>'
             f'<span class="ft-stat" title="Speed"><i>SPD</i>{esc(spd)}</span>')
    return template("hud_enemy").substitute(role=esc((state.enemy_role or "").upper()), name=esc(t.name), stats=stats)


# ------------------------------------------------------------ caption, ticker

def actor_html(kind: str, label: str, portrait: str | None = None) -> str:
    if kind == "enemy":
        icon = f'<img src="{esc(portrait)}" alt="">' if portrait else "<i>&#9760;</i>"
    else:
        icon = f"<i>{ACTOR_ICONS.get(kind, ACTOR_ICONS['all'])}</i>"
    kind = kind if kind in ("enemy", "players") else "all"
    return f'<span class="ft-actor {kind}">{icon}<b>{esc(label)}</b></span>'


def enemy_roll_html(actions: int) -> str:
    word = "Action" if actions == 1 else "Actions"
    return (f'<div class="ft-roll"><span class="ft-die">&#127922;</span><b>ROLL FOR THE ENEMY!</b>'
            f'<span class="ft-combo-chip">{int(actions)} {word}</span></div>')


def ticker_html(state: GameState) -> str:
    entry = next((e for e in reversed(state.log) if e.kind != "hint"), None)
    if entry is None:
        return '<div class="ft-ticker-line" data-fx="static">&nbsp;</div>'
    return (f'<div class="ft-ticker-line" data-fx="act-{int(entry.index)}">'
            f'<b>&#9654;</b> {esc(entry.text)}</div>')


def empty_zone_html(zone: str, text: str) -> str:
    return f'<div class="ft-empty-zone" data-fx-zone="{esc(zone)}"><span>{esc(text)}</span></div>'
