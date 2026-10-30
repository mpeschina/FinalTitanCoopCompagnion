"""Catalog editor: card image next to its metadata, with validation."""
from __future__ import annotations

import copy

import streamlit as st

from finaltitan.catalog import save_catalog, validate
from ui import images, session


def _save(cat) -> None:
    save_catalog(cat)
    st.cache_resource.clear()
    st.toast("Catalog saved")


def render() -> None:
    session.init()
    st.title("Catalog editor")
    if "edit_catalog" not in st.session_state:
        st.session_state.edit_catalog = copy.deepcopy(session.catalog())
    cat = st.session_state.edit_catalog

    issues = validate()
    if issues:
        with st.expander(f"{len(issues)} validation issue(s)", expanded=False):
            for i in issues:
                st.write(f"- {i}")
    else:
        st.success("Metadata and images are consistent.")

    kind = st.segmented_control("Card type", ["Titans", "Upgrades"], default="Titans", key="ed_kind") or "Titans"
    cards = list(cat.titans.values() if kind == "Titans" else cat.upgrades.values())
    if not cards:
        st.info("No cards.")
        return
    idx_key = f"ed_idx_{kind}"
    idx = min(st.session_state.get(idx_key, 0), len(cards) - 1)

    n1, n2, n3 = st.columns([1, 1, 6])
    if n1.button("Previous", disabled=idx == 0):
        idx -= 1
    if n2.button("Next", disabled=idx >= len(cards) - 1):
        idx += 1
    st.session_state[idx_key] = idx
    card = cards[idx]
    n3.caption(f"{idx + 1} / {len(cards)} · {card.id}")

    left, right = st.columns([3, 2])
    with left:
        images.show(card.image, 640)
    with right:
        key = f"{kind}_{card.id}"
        card.name = st.text_input("Name", card.name, key=f"{key}_name")
        card.expansion = st.text_input("Expansion", card.expansion, key=f"{key}_exp")
        if kind == "Titans":
            card.max_life = int(st.number_input("Max Life (Power)", 0, 99, card.max_life, key=f"{key}_life"))
            card.speed = int(st.number_input("Speed", 0, 99, card.speed, key=f"{key}_spd"))
            card.armor = int(st.number_input("Armor", 0, 20, card.armor, key=f"{key}_arm"))
            card.team_power = st.checkbox("Team Power", card.team_power, key=f"{key}_tp")
            card.legendary_id = st.text_input("Legendary Upgrade id", card.legendary_id, key=f"{key}_leg")
        else:
            card.legendary = st.checkbox("Legendary", card.legendary, key=f"{key}_legend")
        card.advanced = st.checkbox("Advanced", card.advanced, key=f"{key}_adv")
        card.enemy_usable = st.checkbox("Usable by the enemy", card.enemy_usable, key=f"{key}_enemy")
        st.button("Save to CSV", type="primary", on_click=_save, args=(cat,))
