"""Arena page: the one-screen enemy display (fight screen) with guide, command pad, and FX overlay."""
from __future__ import annotations

import random

import streamlit as st

from finaltitan import events as ev
from finaltitan.guide import LEVELS, Guidance, guide
from finaltitan.state import COUNT_TOKENS, GameState
from presentation import render as view
from presentation.fx_layer import fx_layer
from presentation.render import esc
from ui import components, session

FIGHT_ENDS = {
    "enemy_defeated": "Enemy is defeated (Defeat icon / effect)",
    "player_defeated": "Our Titan is defeated",
    "both_defeated": "Both are defeated at the same time",
    "enemy_returned": "Enemy returns to its bench",
    "player_returned": "Our Titan returns to its bench",
}


def _md(html: str) -> None:
    st.markdown(html, unsafe_allow_html=True)


# ------------------------------------------------- reveal dialog (fallback)

@st.dialog("Revealed", width="large")
def _reveal_dialog(reveals) -> None:
    cat = session.catalog()
    for col, r in zip(st.columns(len(reveals)), reveals):
        with col:
            if r.kind == "titan":
                card = cat.titans.get(r.card_id)
                where = "enters the arena" if r.where == "arena" else "joins the enemy bench"
                st.subheader(f"{card.name if card else r.card_id} {where}")
            else:
                card = cat.upgrades.get(r.card_id)
                st.subheader(f"Enemy Upgrade: {card.name if card else r.card_id}")
            components.card_image(card.image if card else None, 900)
    if st.button("Continue", type="primary"):
        st.rerun()


def _maybe_reveal(state: GameState, cinematics: bool) -> None:
    ss = st.session_state
    if state.last_reveals and ss.reveal_marker < state.event_count:
        ss.reveal_marker = state.event_count
        if cinematics:
            return
        latest = {(r.kind, r.card_id): r for r in state.last_reveals}
        _reveal_dialog(list(latest.values()))


# ----------------------------------------------------------------------- HUD

def _hud(state: GameState) -> None:
    _md(view.hud_players_html(state))
    st.button("↶ Undo", on_click=session.undo, disabled=not st.session_state.events, key="undo_top")
    with st.popover("☰ Menu"):
        ss = st.session_state
        ss._fight_guidance = session.settings().level
        st.selectbox("Guidance level", LEVELS, key="_fight_guidance",
                     on_change=lambda: ss.update(opt_level=ss._fight_guidance, beginner_progress=None))
        st.button("📜 Battle log and save", key="menu_log", on_click=session.go, args=("log",), width="stretch")
        st.button("⚙ Setup", key="menu_setup", on_click=session.go, args=("setup",), width="stretch")
        st.button("New game", key="menu_new", on_click=session.new_game, width="stretch")
    _md(view.hud_center_html(state))
    _md(view.hud_enemy_html(state))


# --------------------------------------------------------------------- stage

def _stage(state: GameState, cat, marks) -> None:
    t = state.arena
    if t is None:
        text = "ARENA EMPTY" if state.phase not in ("victory", "defeat") else state.phase.upper() + "!"
        _md(view.empty_zone_html("arena", text))
        return
    if t.life is not None:
        _md(view.life_bar_html(t, marks))
    card = view.card_html(cat, "titans", t.card_id, cls=view.arena_classes(t), marks=marks,
                            overlay=view.arena_overlay(t, marks))
    _md(f'<div class="ft-arena-zone" data-fx-zone="arena">{card}</div>')
    if t.life is not None:
        with st.container(key="ft_charge_row", horizontal=True):
            key = f"charge_{state.event_count}"
            st.toggle("Charge flipped", value=t.charged, key=key,
                      help="Flip when the enemy rolls Charge. Turn off again when the Ultimate fires on the enemy's turn.",
                      on_change=lambda: session.dispatch(ev.FLAG, target=t.card_id, flag="charged", value=bool(st.session_state[key])))
            if t.charged:
                _md('<span class="ft-ult-ready">ULTIMATE READY</span>')
    if t.legendary_upgrade:
        st.caption(f"Legendary Upgrade: {t.legendary_upgrade}")


# --------------------------------------------------- side: next, deck, pile

def _side(state: GameState, cat, marks) -> None:
    if state.bench:
        nxt = state.bench[0]
        label = f'<div class="ft-zone-label">NEXT ENEMY &middot; <b>{esc(nxt.name)}</b></div>'
        card = view.card_html(cat, "titans", nxt.card_id, cls="next enemy", marks=marks, overlay=view.badges_html(nxt, marks))
    else:
        label = '<div class="ft-zone-label">NEXT ENEMY</div>'
        card = '<div class="ft-next-empty"></div>'
    deck = view.stack_html(cat, "titans", len(state.deck), "deck", "DECK")
    pile = "".join(view.card_html(cat, "titans", cid, cls="ko", size="thumb", fx_prefix="ko") for cid in state.defeated)
    _md(
        f'<div class="ft-side-row ft-zoomable"><div class="ft-side-col" data-fx-zone="next-enemy">{label}{card}</div>'
        f'<div class="ft-side-col">{deck}<div class="ft-zone-label">DEFEATED <b>{len(state.defeated)}/{int(state.total)}</b></div>'
        f'<div class="ft-defeated" data-fx-zone="graveyard">{pile}</div></div></div>'
    )


def _upgrades(state: GameState, cat, marks) -> None:
    ups = state.active_upgrades
    hand = view.stack_html(cat, "upgrades", len(state.upgrade_hand), "hand", "HAND")
    head = f'<div class="ft-up-head">{hand}<div class="ft-zone-label">ENEMY UPGRADES &middot; <b>{len(ups)}</b> active</div></div>'
    cards = "".join(
        "<div>" + view.card_html(cat, "upgrades", uid, cls="upgrade", marks=marks,
                                   overlay='<span class="ft-new">NEW!</span>' if uid in state.new_upgrades else "") + "</div>"
        for uid in ups
    )
    many = " many" if len(ups) > 6 else ""
    grid = cards or '<div class="ft-up-none">None revealed yet.</div>'
    _md(f'{head}<div class="ft-upgrade-grid ft-zoomable{many}" data-fx-zone="upgrades">{grid}</div>')


# --------------------------------------------------------------- caption box

def _guide_panel(state: GameState, g: Guidance, cat) -> None:
    portrait = view.card_src(cat, "titans", state.arena.card_id, "thumb") if state.arena else None
    confirmation = None
    with st.container(key="ft_guide_content"):
        _md(view.actor_html(g.actor_kind, g.actor_label, portrait))
        if g.confirms:
            marker = (g.step, state.event_count)
            progress = st.session_state.get("beginner_progress")
            step = progress[1] if progress and progress[0] == marker else 0
            st.caption(f"Step {step + 1} of {len(g.lines)}")
            st.markdown(g.lines[step])
            if step < len(g.lines) - 1:
                confirmation = g.confirms[step] if step < len(g.confirms) else "Confirm"
        elif g.step.startswith("cleanup_") and len(g.lines) > 1:
            _md(f'<p class="ft-guide-head">{esc(g.lines[0])}</p>')
            st.markdown("\n".join(f"- {line}" for line in g.lines[1:]))
        else:
            if g.step == "enemy_turn" and state.arena is not None:
                _md(view.enemy_roll_html(1 + state.arena.statuses.action))
            for line in g.lines:
                st.markdown(line)
        if confirmation is None:
            for h in g.hints:
                st.caption(f"💡 {h}")
            if g.why:
                with st.expander("Why?"):
                    st.write(g.why)
                    for text, path in g.refs:
                        st.caption(f"Rules: {text} ({path})")
    with st.container(key="ft_guide_actions"):
        if confirmation is not None:
            label = confirmation
            st.button(label, type="primary", key=f"beginner_{g.step}_{step}",
                      on_click=lambda: st.session_state.update(beginner_progress=(marker, step + 1)), width="stretch")
        elif g.primary:
            for i, (col, p) in enumerate(zip(st.columns(len(g.primary)), g.primary)):
                col.button(p.label, type="primary", key=f"primary_{g.step}_{i}",
                           on_click=session.dispatch, args=(p.kind,), kwargs=p.args, width="stretch")


# --------------------------------------------------------------- command pad

def _controls(state: GameState, cat) -> None:
    ss = st.session_state
    if state.phase in ("victory", "defeat"):
        st.button("Try again" if state.phase == "defeat" else "New game", on_click=session.new_game, key="new_after",
                  type="primary", width="stretch")
        return
    t = state.arena
    if t is None or not state.in_fight():
        components.label("Command pad · waiting for the next fight")
        return
    components.label("Damage to the enemy")
    with st.container(key="ft_dmg_row", horizontal=True):
        for i in range(1, 7):
            st.button(str(i), key=f"dmg_q{i}", on_click=session.dispatch, args=(ev.DAMAGE,), kwargs={"base": i})
        with st.popover("…"):
            st.number_input("Base damage", 0, 99, 1, key="dmg_base")
            st.number_input("Bonus (e.g. your Power tokens)", -20, 20, 0, key="dmg_bonus")
            st.checkbox("Canceled (set to 0)", key="dmg_cancel")
            use_rep = st.checkbox("Replace damage with", key="dmg_use_rep")
            st.number_input("Replacement", 0, 99, 0, key="dmg_rep", disabled=not use_rep)

            def apply_damage() -> None:
                session.dispatch(ev.DAMAGE, base=int(ss.dmg_base), bonus=int(ss.dmg_bonus), cancel=bool(ss.dmg_cancel),
                                 replacement=int(ss.dmg_rep) if ss.dmg_use_rep else None)
            st.button("Deal damage", on_click=apply_damage, type="primary", key="dmg_go")
    st.caption(f"Armor {t.armor} is subtracted; Dodge and Minion apply automatically.")

    with st.container(key="ft_cmd_row", horizontal=True):
        with st.popover("♥ Heal", width="stretch"):
            st.number_input("Amount", 1, 99, 1, key="heal_amt")
            h1, h2, h3 = st.columns(3)
            h1.button("Heal", on_click=lambda: session.dispatch(ev.HEAL, amount=int(ss.heal_amt)), key="heal_go")
            h2.button("Life +", on_click=lambda: session.dispatch(ev.LIFE_ADJUST, delta=int(ss.heal_amt)), key="life_up")
            h3.button("Life −", on_click=lambda: session.dispatch(ev.LIFE_ADJUST, delta=-int(ss.heal_amt)), key="life_down")

        with st.popover("◉ Tokens", width="stretch"):
            enemies = state.enemies()
            ids = [e.card_id for e in enemies]
            if ss.get("tok_target") not in ids:
                ss.tok_target = ids[0]
            st.selectbox("Enemy Titan", ids, format_func=lambda c: next(e.name for e in enemies if e.card_id == c), key="tok_target")
            st.selectbox("Token", [*COUNT_TOKENS, "blessed", "cursed"], format_func=str.capitalize, key="tok_kind")
            st.number_input("Amount", 1, 20, 1, key="tok_amt")
            t1, t2 = st.columns(2)
            t1.button("Add", on_click=lambda: session.dispatch(ev.TOKEN, target=ss.tok_target, token=ss.tok_kind, delta=int(ss.tok_amt)), key="tok_add")
            t2.button("Remove", on_click=lambda: session.dispatch(ev.TOKEN, target=ss.tok_target, token=ss.tok_kind, delta=-int(ss.tok_amt)), key="tok_rm")
            st.divider()
            st.toggle("Ultimate Form", value=t.ultimate_form, key=f"uf_{state.event_count}",
                      on_change=lambda: session.dispatch(ev.FLAG, target=t.card_id, flag="ultimate_form", value=not t.ultimate_form))

        with st.popover("✖ End fight", width="stretch"):
            for reason, text in FIGHT_ENDS.items():
                st.button(text, key=f"end_{reason}", on_click=session.dispatch, args=(ev.FIGHT_END,), kwargs={"reason": reason}, width="stretch")

        with st.popover("⋯ More", width="stretch"):
            s1, s2 = st.columns([2, 1], vertical_alignment="bottom")
            s1.number_input("Enemy Speed", 0, 99, t.speed, key=f"spd_val_{state.event_count}")
            s2.button("Set", key="spd_set", on_click=lambda: session.dispatch(ev.SPEED, value=int(ss[f"spd_val_{state.event_count}"])))
            if state.bench:
                st.selectbox("Swap enemy with", [b.card_id for b in state.bench],
                             format_func=lambda c: next(b.name for b in state.bench if b.card_id == c), key="swap_with")
                st.button("Swap", on_click=lambda: session.dispatch(ev.SWAP, with_id=ss.swap_with), key="swap_go")
            used = set(state.upgrade_hand) | set(state.active_upgrades)
            pool = [u.id for u in cat.upgrades.values() if u.enemy_usable and u.id not in used]
            st.button("Add a face-down Upgrade to the enemy hand", disabled=not pool, key="more_up",
                      on_click=lambda: session.dispatch(ev.ADD_ENEMY_UPGRADE, card_id=random.choice(pool)))
            st.text_input("Log note", key="note_txt")
            st.button("Add note", key="note_go", on_click=lambda: ss.note_txt.strip() and session.dispatch(ev.NOTE, text=ss.note_txt.strip()))


def _ticker(state: GameState) -> None:
    _md(view.ticker_html(state))
    st.button("📜 Log", key="ticker_log", on_click=session.go, args=("log",))


# ------------------------------------------------------------------- page

def render() -> None:
    session.init()
    ss = st.session_state
    state = session.game()
    if state is None:
        st.info("No game in progress.")
        st.button("Go to Setup", on_click=session.go, args=("setup",))
        return
    cat = session.catalog()
    fx_set = session.fx_settings()
    _maybe_reveal(state, cinematics=fx_set.intensity != "Off" and fx_set.cinematics != "Off")
    g = guide(state, session.settings())
    marks = ss.fx_marks

    if state.phase == "start":
        with st.container(key="ft_caption_start"):
            for w in dict.fromkeys(ss.get("warnings") or []):
                st.warning(w)
            _guide_panel(state, g, cat)
    else:
        with st.container(key="ft_screen"):
            with st.container(key="ft_hud", horizontal=True, vertical_alignment="center"):
                _hud(state)
            with st.container(key="ft_stage"):
                _stage(state, cat, marks)
            with st.container(key="ft_side"):
                _side(state, cat, marks)
            with st.container(key="ft_upgrades"):
                _upgrades(state, cat, marks)
            with st.container(key="ft_caption"):
                _guide_panel(state, g, cat)
            with st.container(key="ft_pad"):
                _controls(state, cat)
            with st.container(key="ft_ticker", horizontal=True, vertical_alignment="center"):
                _ticker(state)
    assets = {"titan_back": view.back_src(cat, "titans"), "upgrade_back": view.back_src(cat, "upgrades")}
    fx_layer(ss.fx_queue, fx_set, assets)

