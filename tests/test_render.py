import json
from dataclasses import replace

from finaltitan.catalog import Catalog, load_catalog
from finaltitan.state import EnemyTitan
from presentation import fx, render
from presentation.fx_layer import payload_html

CAT = load_catalog()
TID = next(iter(CAT.titans))
UID = next(iter(CAT.upgrades))


def evil_catalog() -> Catalog:
    t = replace(CAT.titans[TID], name='<script>alert(1)</script>"')
    return Catalog({TID: t}, dict(CAT.upgrades), CAT.titan_back)


def titan(**kw) -> EnemyTitan:
    base = dict(card_id=TID, name="X", max_life=10, base_speed=3, life=10)
    base.update(kw)
    return EnemyTitan(**base)


def test_card_html_escapes_names_and_serves_static_webp():
    html = render.card_html(evil_catalog(), "titans", TID)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert f'src="app/static/cards/titans/{TID}.webp"' in html
    assert (render.STATIC / f"cards/titans/{TID}.webp").exists()
    assert "\n" not in html


def test_image_paths_only_from_whitelisted_ids():
    assert render.card_src(CAT, "titans", "../../etc/passwd") is None
    assert render.card_src(CAT, "titans", "no_such_card") is None
    assert render.card_src(CAT, "secret", TID) is None
    assert render.card_src(CAT, "upgrades", UID, "thumb").endswith(f"/cards/thumbs/upgrades/{UID}.webp")


def test_templates_are_single_line_for_markdown():
    for name in ("card", "lifebar", "hud_players", "hud_center", "hud_enemy"):
        text = render.template(name).template
        assert "\n" not in text and not text.startswith(" ")


def test_life_bar_animates_only_for_the_marked_action():
    t = titan(life=4)
    static = render.life_bar_html(t, {})
    assert 'data-fx="static"' in static and "anim" not in static and "--from:0.400" in static
    marked = render.life_bar_html(t, {f"life-{TID}": (7, 0.9)})
    assert 'data-fx="act-7"' in marked and "anim" in marked and "--from:0.900;--to:0.400" in marked
    assert "--pips:10" in marked


def test_heal_marks_life_bar_as_rising():
    assert " up " in render.life_bar_html(titan(life=8), {f"life-{TID}": (3, 0.2)})


def test_badges_pop_once_and_show_tokens():
    t = titan()
    t.statuses.poison = 2
    t.statuses.blessed_cursed = "cursed"
    plain = render.badges_html(t)
    assert "tok-poison" in plain and "<b>2</b>" in plain and "YOU pick" in plain and " pop" not in plain
    popped = render.badges_html(t, {f"badge-{TID}-poison": (5, 1)})
    assert 'tok-poison pop" data-fx="act-5"' in popped


def test_card_marks_set_layer2_classes():
    hit = render.card_html(CAT, "titans", TID, cls="arena", marks={f"card-{TID}": (4, "hit2")})
    assert "l2-hit2" in hit and 'data-fx="act-4"' in hit
    arrive = render.card_html(CAT, "upgrades", UID, marks={f"card-{UID}": (4, "arrive")})
    assert "ft-arriving" in arrive
    ko = render.card_html(CAT, "titans", TID, fx_prefix="ko", size="thumb")
    assert f'data-fx-id="ko-{TID}"' in ko


def test_arena_classes_flag_low_life_and_charge():
    assert render.arena_classes(titan(life=3, charged=True)) == "arena enemy low charged"
    assert "low" not in render.arena_classes(titan(life=8))


def test_pips_and_hud_values_are_ints():
    assert render.pips_html(2, 3, "titan").count(" on") == 2
    assert render.pips_html("2", "3", "ko").count('class="pip') == 3


def test_payload_cannot_break_out_of_script():
    cue = fx.Cue("act-1-0", "taunt", "card-x", {"text": "</script><script>alert(1)</script>"})
    html = payload_html([cue.to_dict()], fx.FxSettings(), {"titan_back": None, "upgrade_back": None})
    assert html.count("</script>") == 1
    start = html.index("var payload = ") + len("var payload = ")
    payload = json.loads(html[start:html.index(";\n", start)].replace("<\\/", "</"))
    assert payload["cues"][0]["params"]["text"].startswith("</script>")
    assert payload["settings"]["intensity"] == "Full"
