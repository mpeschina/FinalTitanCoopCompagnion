"""Arena page: the one-screen enemy display (fight screen) with guide, command pad, and FX overlay."""
from __future__ import annotations

import random

import streamlit as st

from finaltitan import dice, events as ev
from finaltitan.guide import LEVELS, Guidance, guide
from finaltitan.engine import FIGHT_END_REASONS
from finaltitan.state import COUNT_TOKENS, GameState
from presentation import fx
from presentation import render as view
from presentation.fx_layer import fx_layer
from presentation.render import esc
from ui import components, session

def _md(html: str) -> None:
    st.markdown(html, unsafe_allow_html=True)


# ------------------------------------------------- reveal dialog (fallback)

def _reveal_body(reveals) -> None:
    cat, tr = session.catalog(), session.translator()
    for col, r in zip(st.columns(len(reveals)), reveals):
        with col:
            if r.kind == "titan":
                card = cat.titans.get(r.card_id)
                where = "arena.enters_arena" if r.where == "arena" else "arena.joins_bench"
                st.subheader(tr(where, name=card.name if card else r.card_id))
            else:
                card = cat.upgrades.get(r.card_id)
                st.subheader(tr("arena.enemy_upgrade", name=card.name if card else r.card_id))
            components.card_image(cat.card_image(card, session.lang()) if card else None, 900)
    if st.button(tr("arena.continue"), type="primary"):
        st.rerun()


def _reveal_dialog(reveals) -> None:
    # The dialog title is fixed when the decorator runs, so the dialog is built per call in the current language.
    st.dialog(session.tr("arena.revealed"), width="large")(_reveal_body)(reveals)


def _maybe_reveal(state: GameState, cinematics: bool) -> None:
    ss = st.session_state
    if state.last_reveals and ss.reveal_marker < state.event_count:
        ss.reveal_marker = state.event_count
        if cinematics:
            return
        latest = {(r.kind, r.card_id): r for r in state.last_reveals}
        _reveal_dialog(list(latest.values()))


# ----------------------------------------------------------------------- HUD

def _fx_widget(widget, label: str, name: str, *args, **kw):
    """A menu widget for an FX setting. Its value lives in a plain session key, so it survives the pages
    where the menu is not rendered."""
    ss = st.session_state
    key = f"_{name}"
    ss[key] = getattr(session.fx_settings(), name)
    return widget(label, *args, key=key, on_change=lambda: ss.update({f"fx_{name}": ss[key]}), **kw)


def _fx_menu() -> None:
    tr = session.translator()
    opt = lambda v: tr(f"opt.{v}")  # noqa: E731
    _fx_widget(st.selectbox, tr("fx.intensity"), "intensity", fx.INTENSITIES, help=tr("fx.intensity_help"), format_func=opt)
    _fx_widget(st.selectbox, tr("fx.cinematics"), "cinematics", fx.CINEMATICS, format_func=opt)
    _fx_widget(st.select_slider, tr("fx.speed"), "speed", fx.SPEEDS, format_func=lambda v: f"{v:g}×")
    sound = _fx_widget(st.toggle, tr("fx.sound"), "sound")
    _fx_widget(st.slider, tr("fx.volume"), "volume", 0.0, 1.0, step=0.05, disabled=not sound)
    _fx_widget(st.toggle, tr("fx.taunts"), "taunts")
    _fx_widget(st.selectbox, tr("fx.ko_style"), "ko_style", fx.KO_STYLE_OPTIONS, format_func=opt)
    _fx_widget(st.toggle, tr("fx.idle"), "idle")
    _fx_widget(st.selectbox, tr("fx.reduced_motion"), "reduced_motion", fx.REDUCED_MOTION,
               help=tr("fx.reduced_motion_help"), format_func=opt)


def _hud(state: GameState) -> None:
    tr, lang = session.translator(), session.lang()
    _md(view.hud_players_html(state, lang))
    st.button(tr("menu.undo"), on_click=session.undo, disabled=not st.session_state.events, key="undo_top")
    with st.popover(tr("menu.title"), key="menu_popover"):
        ss = st.session_state
        components.language_picker("menu", width=54)
        ss._fight_guidance = session.settings().level
        st.selectbox(tr("guidance.label"), LEVELS, key="_fight_guidance", format_func=lambda v: tr(f"opt.{v}"),
                     on_change=lambda: ss.update(opt_level=ss._fight_guidance, beginner_progress=None))
        with st.expander(tr("menu.effects"), key="menu_effects"):
            _fx_menu()
        st.button(tr("menu.log"), key="menu_log", on_click=session.go, args=("log",), width="stretch")
        if session.debug():
            st.button(tr("menu.catalog"), key="menu_catalog", on_click=session.go, args=("catalog",), width="stretch")
        st.button(tr("menu.new_game"), key="menu_new", on_click=session.new_game, width="stretch")
    _md(view.hud_center_html(state, lang))
    _md(view.hud_enemy_html(state, lang))


# --------------------------------------------------------------------- stage

def _stage(state: GameState, cat, marks) -> None:
    tr = session.translator()
    t = state.arena
    if t is None:
        text = tr("arena.empty") if state.phase not in ("victory", "defeat") else tr(f"arena.{state.phase}")
        _md(view.empty_zone_html("arena", text))
        return
    if t.life is not None:
        _md(view.life_bar_html(t, marks))
    card = view.card_html(cat, "titans", t.card_id, cls=view.arena_classes(t), marks=marks,
                            overlay=view.arena_overlay(t, marks, session.lang()), lang=session.lang())
    _md(f'<div class="ft-arena-zone" data-fx-zone="arena">{card}</div>')
    if t.life is not None:
        with st.container(key="ft_charge_row", horizontal=True):
            key = f"charge_{state.event_count}"
            st.toggle(tr("arena.charge"), value=t.charged, key=key, help=tr("arena.charge_help"),
                      on_change=lambda: session.dispatch(ev.FLAG, target=t.card_id, flag="charged", value=bool(st.session_state[key])))
            if t.charged:
                _md(f'<span class="ft-ult-ready">{esc(tr("arena.ult_ready"))}</span>')
    if t.legendary_upgrade:
        st.caption(tr("arena.legendary", name=t.legendary_upgrade))


# --------------------------------------------------- side: next, deck, pile

def _side(state: GameState, cat, marks) -> None:
    tr, lang = session.translator(), session.lang()
    if state.bench:
        nxt = state.bench[0]
        label = f'<div class="ft-zone-label">{esc(tr("zone.next_enemy"))} &middot; <b>{esc(nxt.name)}</b></div>'
        card = view.card_html(cat, "titans", nxt.card_id, cls="next enemy", marks=marks, overlay=view.badges_html(nxt, marks, lang), lang=lang)
    else:
        label = f'<div class="ft-zone-label">{esc(tr("zone.next_enemy"))}</div>'
        card = '<div class="ft-next-empty"></div>'
    deck = view.stack_html(cat, "titans", len(state.deck), "deck", tr("zone.deck"), lang)
    pile = "".join(view.card_html(cat, "titans", cid, cls="ko", size="thumb", fx_prefix="ko", lang=lang) for cid in state.defeated)
    _md(
        f'<div class="ft-side-row ft-zoomable"><div class="ft-side-col" data-fx-zone="next-enemy">{label}{card}</div>'
        f'<div class="ft-side-col">{deck}<div class="ft-zone-label">{esc(tr("zone.defeated"))} <b>{len(state.defeated)}/{int(state.total)}</b></div>'
        f'<div class="ft-defeated" data-fx-zone="graveyard">{pile}</div></div></div>'
    )


def _upgrades(state: GameState, cat, marks) -> None:
    tr, lang = session.translator(), session.lang()
    ups = state.active_upgrades
    hand = view.stack_html(cat, "upgrades", len(state.upgrade_hand), "hand", tr("zone.hand"), lang)
    head = (f'<div class="ft-up-head">{hand}<div class="ft-zone-label">{esc(tr("zone.enemy_upgrades"))} &middot; '
            f'<b>{len(ups)}</b> {esc(tr("zone.active"))}</div></div>')
    new = f'<span class="ft-new">{esc(tr("card.new"))}</span>'
    cards = "".join(
        "<div>" + view.card_html(cat, "upgrades", uid, cls="upgrade", marks=marks,
                                   overlay=new if uid in state.new_upgrades else "", lang=lang) + "</div>"
        for uid in ups
    )
    many = " many" if len(ups) > 6 else ""
    grid = cards or f'<div class="ft-up-none">{esc(tr("zone.none_revealed"))}</div>'
    _md(f'{head}<div class="ft-upgrade-grid ft-zoomable{many}" data-fx-zone="upgrades">{grid}</div>')


# --------------------------------------------------------------- caption box

def _roll_panel(state: GameState) -> None:
    """Enemy turn: the Action tracker, what the latest roll asks for, and the picks for a Blessed or Cursed roll."""
    tr, lang = session.translator(), session.lang()
    _md(view.roll_tracker_html(state, lang))
    hint = dice.roll_hint(state)
    last = state.turn_rolls[-1] if state.turn_rolls else None
    # Expert mode drops the "what to do with this result" lines; the picks and the doubles prompt stay.
    if hint is not None and (session.settings().level != "Expert" or not hint.key.startswith("roll.result_")):
        st.markdown(session.text(hint))
    if last is None or state.arena is None:
        return
    if last.pending:
        with st.container(key="ft_roll_pick", horizontal=True):
            for i, f in enumerate(last.faces):
                st.button(tr("roll.pick_die", face=tr(f"die.{f}")), key=f"ft_pick_{i}_{f}", width="stretch",
                          on_click=session.dispatch, args=(ev.ROLL_PICK,), kwargs={"index": i})
    elif last.doubles and state.arena.statuses.blessed_cursed == last.token != "none":
        st.button(tr("roll.remove_token", token=tr(f"token.{last.token}")), key="ft_remove_token", width="stretch",
                  on_click=session.dispatch, args=(ev.TOKEN,),
                  kwargs={"target": state.arena.card_id, "token": last.token, "delta": -1})


def _guide_panel(state: GameState, g: Guidance, cat) -> None:
    tr = session.translator()
    portrait = view.card_src(cat, "titans", state.arena.card_id, "thumb", session.lang()) if state.arena else None
    confirmation = None
    with st.container(key="ft_guide_content"):
        # Style markers sit in their own hidden blocks. Every step emits the same number of them: Streamlit keeps
        # leftover elements from the previous run on screen until the rerun ends, which would resize the box.
        if session.settings().level == "Expert":
            _md('<span class="ft-expert"></span>')
        _md('<span class="ft-roll"></span>' if g.step == "enemy_turn" and state.arena is not None else '<span class="ft-slot"></span>')
        _md(view.actor_html(g.actor_kind, g.actor_label, portrait))
        if g.confirms:
            marker = (g.step, state.event_count)
            progress = st.session_state.get("beginner_progress")
            step = progress[1] if progress and progress[0] == marker else 0
            st.caption(tr("guide.step", n=step + 1, total=len(g.lines)))
            st.markdown(g.lines[step])
            if step < len(g.lines) - 1:
                confirmation = g.confirms[step] if step < len(g.confirms) else tr("guide.confirm")
        elif g.step.startswith("cleanup_") and len(g.lines) > 1:
            _md(f'<p class="ft-guide-head">{esc(g.lines[0])}</p>')
            st.markdown("\n".join(f"- {line}" for line in g.lines[1:]))
        elif g.step == "enemy_turn" and state.arena is not None:
            if g.lines:
                st.markdown("\n".join(f"{i}. {line}" for i, line in enumerate(g.lines[:3], 1)))
            _roll_panel(state)
            for line in g.lines[3:]:
                st.caption(line)
        else:
            for line in g.lines:
                st.markdown(line)
        if confirmation is None:
            for h in g.hints:
                st.caption(f"💡 {h}")
            if g.why:
                with st.expander(tr("guide.why"), key="guide_why"):
                    st.write(g.why)
                    for text, path in g.refs:
                        st.caption(tr("guide.rules", text=text, path=path))
    with st.container(key="ft_guide_actions"):
        if confirmation is not None:
            label = confirmation
            st.button(label, type="primary", key=f"beginner_{g.step}_{step}",
                      on_click=lambda: st.session_state.update(beginner_progress=(marker, step + 1)), width="stretch")
        elif g.primary:
            with st.container(key="ft_guide_buttons", horizontal=True):
                if g.step == "enemy_turn":
                    done = state.arena is not None and len(state.turn_rolls) >= dice.slots(state)
                    st.button(tr("roll.button"), key="ft_enemy_roll_done" if done else "ft_enemy_roll", type="primary",
                              on_click=session.roll_enemy, width="stretch",
                              help=tr("roll.button_done") if done else None)
                for i, p in enumerate(g.primary):
                    st.button(p.label, type="primary", key=f"primary_{g.step}_{i}",
                              on_click=session.dispatch, args=(p.kind,), kwargs=p.args, width="stretch")
                if g.step == "players_turn":
                    _md('<span class="ft-slot"></span>')  # same element count as the enemy turn's Roll + End


# --------------------------------------------------------------- command pad

def _controls(state: GameState, cat) -> None:
    ss, tr = st.session_state, session.translator()
    if state.phase in ("victory", "defeat"):
        if state.phase == "defeat":  # the exact same matchup again; New game stays in the menu
            st.button(tr("pad.rematch"), on_click=session.rematch, key="new_after", type="primary", width="stretch")
            st.caption(tr("pad.rematch_note"))
        else:
            st.button(tr("pad.new_game"), on_click=session.new_game, key="new_after", type="primary", width="stretch")
        return
    t = state.arena
    if t is None or not state.in_fight():
        components.label(tr("pad.waiting"))
        return
    components.label(tr("pad.damage"))
    with st.container(key="ft_dmg_row", horizontal=True):
        for i in range(1, 7):
            st.button(str(i), key=f"dmg_q{i}", on_click=session.dispatch, args=(ev.DAMAGE,), kwargs={"base": i})
        with st.popover("…", key="dmg_more"):
            st.number_input(tr("pad.base"), 0, 99, 1, key="dmg_base")
            st.number_input(tr("pad.bonus"), -20, 20, 0, key="dmg_bonus")
            st.checkbox(tr("pad.cancel"), key="dmg_cancel")
            use_rep = st.checkbox(tr("pad.replace"), key="dmg_use_rep")
            st.number_input(tr("pad.replacement"), 0, 99, 0, key="dmg_rep", disabled=not use_rep)

            def apply_damage() -> None:
                session.dispatch(ev.DAMAGE, base=int(ss.dmg_base), bonus=int(ss.dmg_bonus), cancel=bool(ss.dmg_cancel),
                                 replacement=int(ss.dmg_rep) if ss.dmg_use_rep else None)
            st.button(tr("pad.deal"), on_click=apply_damage, type="primary", key="dmg_go")
    st.caption(tr("pad.armor_note", armor=t.armor))

    with st.container(key="ft_cmd_row", horizontal=True):
        with st.popover(tr("pad.heal_menu"), width="stretch", key="pad_heal"):
            st.number_input(tr("pad.amount"), 1, 99, 1, key="heal_amt")
            h1, h2 = st.columns(2)
            h1.button(tr("pad.heal"), on_click=lambda: session.dispatch(ev.HEAL, amount=int(ss.heal_amt)), key="heal_go")
            h2.button(tr("pad.life_up"), on_click=lambda: session.dispatch(ev.LIFE_ADJUST, delta=int(ss.heal_amt)), key="life_up")

        with st.popover(tr("pad.tokens_menu"), width="stretch", key="pad_tokens"):
            enemies = state.enemies()
            ids = [e.card_id for e in enemies]
            if ss.get("tok_target") not in ids:
                ss.tok_target = ids[0]
            st.selectbox(tr("pad.enemy_titan"), ids, format_func=lambda c: next(e.name for e in enemies if e.card_id == c), key="tok_target")
            st.selectbox(tr("pad.token"), [*COUNT_TOKENS, "blessed", "cursed"], format_func=lambda v: tr(f"token.{v}"), key="tok_kind")
            st.number_input(tr("pad.amount"), 1, 20, 1, key="tok_amt")
            t1, t2 = st.columns(2)
            t1.button(tr("pad.add"), on_click=lambda: session.dispatch(ev.TOKEN, target=ss.tok_target, token=ss.tok_kind, delta=int(ss.tok_amt)), key="tok_add")
            t2.button(tr("pad.remove"), on_click=lambda: session.dispatch(ev.TOKEN, target=ss.tok_target, token=ss.tok_kind, delta=-int(ss.tok_amt)), key="tok_rm")
            st.divider()
            st.toggle(tr("flag.ultimate_form"), value=t.ultimate_form, key=f"uf_{state.event_count}",
                      on_change=lambda: session.dispatch(ev.FLAG, target=t.card_id, flag="ultimate_form", value=not t.ultimate_form))

        with st.popover(tr("pad.end_menu"), width="stretch", key="pad_end"):
            for reason in FIGHT_END_REASONS:
                st.button(tr(f"fight_end.{reason}"), key=f"end_{reason}", on_click=session.dispatch, args=(ev.FIGHT_END,), kwargs={"reason": reason}, width="stretch")

        with st.popover(tr("pad.more_menu"), width="stretch", key="pad_more"):
            s1, s2 = st.columns([2, 1], vertical_alignment="bottom")
            s1.number_input(tr("pad.speed"), 0, 99, t.speed, key=f"spd_val_{state.event_count}")
            s2.button(tr("pad.set"), key="spd_set", on_click=lambda: session.dispatch(ev.SPEED, value=int(ss[f"spd_val_{state.event_count}"])))
            if state.bench:
                st.selectbox(tr("pad.swap_with"), [b.card_id for b in state.bench],
                             format_func=lambda c: next(b.name for b in state.bench if b.card_id == c), key="swap_with")
                st.button(tr("pad.swap"), on_click=lambda: session.dispatch(ev.SWAP, with_id=ss.swap_with), key="swap_go")
            used = set(state.upgrade_hand) | set(state.active_upgrades)
            pool = [u.id for u in cat.upgrades.values() if u.enemy_usable and u.id not in used]
            st.button(tr("pad.add_upgrade"), disabled=not pool, key="more_up",
                      on_click=lambda: session.dispatch(ev.ADD_ENEMY_UPGRADE, card_id=random.choice(pool)))
            st.text_input(tr("pad.note"), key="note_txt")
            st.button(tr("pad.add_note"), key="note_go", on_click=lambda: ss.note_txt.strip() and session.dispatch(ev.NOTE, text=ss.note_txt.strip()))


def _ticker(state: GameState) -> None:
    _md(view.ticker_html(state, session.lang()))
    st.button(session.tr("ticker.log"), key="ticker_log", on_click=session.go, args=("log",))


# ------------------------------------------------------------------- page

def render() -> None:
    session.init()
    ss = st.session_state
    state = session.game()
    if state is None:
        st.info(session.tr("common.no_game"))
        st.button(session.tr("common.go_setup"), on_click=session.go, args=("setup",))
        return
    cat = session.catalog()
    fx_set = session.fx_settings()
    _maybe_reveal(state, cinematics=fx_set.intensity != "Off" and fx_set.cinematics != "Off")
    g = guide(state, session.settings())
    marks = ss.fx_marks

    if state.phase == "start":
        with st.container(key="ft_caption_start"):
            for w in dict.fromkeys(session.text(w) for w in ss.get("warnings") or []):
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
            with st.container(key="ft_left"):
                with st.container(key="ft_caption"):
                    _guide_panel(state, g, cat)
                with st.container(key="ft_pad"):
                    _controls(state, cat)
            with st.container(key="ft_ticker", horizontal=True, vertical_alignment="center"):
                _ticker(state)
    assets = {"titan_back": view.back_src(cat, "titans", session.lang()), "upgrade_back": view.back_src(cat, "upgrades")}
    pending = bool(state.turn_rolls and state.turn_rolls[-1].pending)
    fx_layer(ss.fx_queue, fx_set, {**assets, "dice": view.dice_srcs()}, {"pending_pick": pending})

