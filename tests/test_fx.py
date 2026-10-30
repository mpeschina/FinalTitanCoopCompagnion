from finaltitan import events as ev
from finaltitan.catalog import load_catalog
from finaltitan.engine import apply, initial_state, reduce
from finaltitan.events import act
from finaltitan.setup import GameSetup, build_enemy, load_presets
from presentation import fx

CAT = load_catalog()


def make_setup(players=1, difficulty="Easy", seed=3):
    s = GameSetup(players=players, difficulty=difficulty, seed=seed)
    s.player_titans = [t.id for t in CAT.titans.values() if t.enemy_usable][:3 * players]
    build_enemy(s, CAT, load_presets())
    return s


def start(setup=None, *actions):
    setup = setup or make_setup()
    return reduce(initial_state(setup, CAT), [act(ev.BEGIN_GAME), *actions])


def step(state, kind, **args):
    a = act(kind, **args)
    after = apply(state, a)
    return after, fx.cues_for(a, state, after)


def kinds(cues):
    return [c.kind for c in cues]


def first(cues, kind):
    return next(c for c in cues if c.kind == kind)


def test_damage_words_follow_thresholds():
    assert fx.damage_word(0) is None
    assert [fx.damage_word(n) for n in (1, 2, 3, 4, 5, 9)] == ["POW!", "POW!", "BAM!", "BAM!", "KA-BOOM!", "KA-BOOM!"]
    assert [fx.tier(n) for n in (1, 3, 5)] == [1, 2, 3]


def test_damage_hit_cue_carries_life_change():
    s = start()
    life = s.arena.life
    after, cues = step(s, ev.DAMAGE, replacement=1)
    hit = first(cues, "hit")
    assert hit.target == f"card-{s.arena.card_id}"
    assert hit.params == {"amount": 1, "word": "POW!", "tier": 1, "life_from": life, "life_to": life - 1, "max_life": s.arena.max_life}
    assert not hit.blocking


def test_cancelled_damage_is_a_whiff():
    s = start()
    _, cues = step(s, ev.DAMAGE, base=4, cancel=True)
    assert kinds(cues) == ["whiff"]
    assert first(cues, "whiff").params["word"] == "WHIFF!"


def test_armor_dodge_and_minion():
    s = start()
    cid = s.arena.card_id
    s, cues = step(s, ev.TOKEN, target=cid, token="armor", delta=2)
    assert first(cues, "token").params == {"token": "armor", "delta": 2, "value": 2, "where": "arena"}
    armor = s.arena.armor
    s, cues = step(s, ev.DAMAGE, base=armor + 1)
    assert first(cues, "armor").params["from"] == armor + 1 and first(cues, "armor").params["to"] == 1
    s, _ = step(s, ev.TOKEN, target=cid, token="dodge", delta=1)
    s, cues = step(s, ev.DAMAGE, base=armor + 3)
    assert "dodge" in kinds(cues) and "hit" not in kinds(cues)
    s, _ = step(s, ev.TOKEN, target=cid, token="minion", delta=1)
    s, cues = step(s, ev.DAMAGE, base=99)
    assert "minion" in kinds(cues) and "ko" not in kinds(cues)


def test_blessed_removed_poofs():
    s = start()
    cid = s.arena.card_id
    s, cues = step(s, ev.TOKEN, target=cid, token="blessed", delta=1)
    assert first(cues, "token").params["token"] == "blessed"
    _, cues = step(s, ev.TOKEN, target=cid, token="blessed", delta=-1)
    assert kinds(cues) == ["poof"]


def test_charge_off_on_enemy_turn_is_the_ultimate():
    s = start(None, act(ev.SET_STARTER, side="enemy"), act(ev.START_TURN))
    cid = s.arena.card_id
    s, cues = step(s, ev.FLAG, target=cid, flag="charged", value=True)
    assert kinds(cues) == ["charge_on"]
    _, cues = step(s, ev.FLAG, target=cid, flag="charged", value=False)
    assert kinds(cues) == ["ultimate"] and cues[0].blocking
    s, _ = step(s, ev.END_TURN)
    _, cues = step(s, ev.FLAG, target=cid, flag="charged", value=False)
    assert kinds(cues) == ["charge_off"]


def test_set_starter_plays_vs_then_turn_banner():
    s = start()
    _, cues = step(s, ev.SET_STARTER, side="players")
    assert kinds(cues) == ["vs", "turn_banner"]
    assert cues[0].blocking and cues[1].params["side"] == "players"


def test_start_turn_lunges_ticks_and_counts_actions():
    s = start(None, act(ev.SET_STARTER, side="enemy"))
    cid = s.arena.card_id
    s, _ = step(s, ev.TOKEN, target=cid, token="fire", delta=1)
    s, _ = step(s, ev.TOKEN, target=cid, token="action", delta=1)
    _, cues = step(s, ev.START_TURN)
    assert kinds(cues) == ["lunge", "tick", "hit", "token", "combo"]
    assert first(cues, "tick").params["word"] == "SIZZLE!"
    assert "word" not in first(cues, "hit").params
    assert first(cues, "combo").params["actions"] == 2


def test_begin_game_order_title_upgrades_arena_bench():
    setup = make_setup()
    s0 = initial_state(setup, CAT)
    a = act(ev.BEGIN_GAME)
    s1 = apply(s0, a)
    cues = fx.cues_for(a, s0, s1, difficulty="Easy")
    assert kinds(cues) == ["title", "reveal_upgrade", "reveal_arena", "reveal_bench"]
    assert cues[0].params["difficulty"] == "Easy"
    assert cues[2].params["from"] == "deck" and cues[2].params["flip"] is True
    assert [c.id for c in cues] == [f"act-1-{i}" for i in range(4)]


def test_reveal_from_bench_does_not_flip():
    s = start()
    nxt = s.bench[0].card_id
    s, _ = step(s, ev.FIGHT_END, reason="enemy_defeated")
    _, cues = step(s, ev.ADVANCE_FIGHT)
    arena = first(cues, "reveal_arena")
    assert arena.target == f"card-{nxt}" and arena.params["from"] == "next-enemy" and not arena.params["flip"]
    assert kinds(cues).index("reveal_upgrade") < kinds(cues).index("reveal_arena")


def test_final_fight_reveals_all_upgrades_after_alert():
    s = start()
    while s.enemy_remaining() > 1:
        s, _ = step(s, ev.FIGHT_END, reason="enemy_defeated")
        if s.enemy_remaining() == 1:
            break
        s, _ = step(s, ev.ADVANCE_FIGHT)
    hand = len(s.upgrade_hand)
    _, cues = step(s, ev.ADVANCE_FIGHT)
    if hand > 1:
        assert kinds(cues)[0] == "final_fight"
        assert kinds(cues).count("reveal_upgrade") == hand


def test_ko_styles():
    s = start()
    life = s.arena.life
    s2, _ = step(s, ev.LIFE_ADJUST, delta=-(life - 2))
    _, cues = step(s2, ev.DAMAGE, replacement=2)
    ko = first(cues, "ko")
    assert ko.blocking and ko.params["style"] == "slash" and ko.params["cuts"] == 2
    assert kinds(cues) == ["hit", "ko"]
    _, cues = step(s2, ev.DAMAGE, replacement=6)
    assert first(cues, "ko").params["style"] == "shatter"
    _, cues = step(s, ev.FIGHT_END, reason="enemy_defeated")
    assert first(cues, "ko").params["style"] == fx.KO_STYLES[(s.fight_no - 1) % 3]
    a = act(ev.FIGHT_END, reason="enemy_defeated")
    forced = fx.ko_params(a, s, apply(s, a), "Dissolve")
    assert forced["style"] == "dissolve"


def test_fire_tick_kill_dissolves():
    s = start(None, act(ev.SET_STARTER, side="enemy"))
    cid = s.arena.card_id
    s, _ = step(s, ev.LIFE_ADJUST, delta=-(s.arena.life - 1))
    s, _ = step(s, ev.TOKEN, target=cid, token="fire", delta=1)
    _, cues = step(s, ev.START_TURN)
    ko = first(cues, "ko")
    assert ko.params["style"] == "dissolve" and ko.params["color"] == "fire"


def test_player_lost_and_retreat():
    s = start()
    _, cues = step(s, ev.FIGHT_END, reason="player_defeated")
    assert kinds(cues) == ["player_lost"]
    assert first(cues, "player_lost").params["left"] == s.player_titans_left - 1
    _, cues = step(s, ev.FIGHT_END, reason="enemy_returned")
    assert kinds(cues) == ["retreat"]


def test_swap_moves_both_cards():
    s = start()
    out, into = s.arena.card_id, s.bench[0].card_id
    _, cues = step(s, ev.SWAP, with_id=into)
    assert kinds(cues) == ["swap"]
    assert cues[0].target == f"card-{into}" and cues[0].params["out"] == f"card-{out}"


def test_defeat_carries_summary():
    setup = make_setup()
    actions = [act(ev.BEGIN_GAME), act(ev.DAMAGE, replacement=1)]
    state = reduce(initial_state(setup, CAT), actions)
    for _ in range(state.player_titans_left - 1):
        actions += [act(ev.FIGHT_END, reason="player_defeated"), act(ev.ADVANCE_FIGHT)]
    state = reduce(initial_state(setup, CAT), actions)
    last = act(ev.FIGHT_END, reason="player_defeated")
    actions.append(last)
    after = apply(state, last)
    summary = fx.game_summary(initial_state(setup, CAT), actions)
    cues = fx.cues_for(last, state, after, summary=summary)
    assert kinds(cues) == ["player_lost", "defeat"]
    assert cues[-1].params["damage"] == 1 and cues[-1].params["titans_left"] == 0


def test_marks_point_at_the_action():
    s = start()
    after, cues = step(s, ev.DAMAGE, replacement=1)
    marks = fx.marks_for(cues, after.event_count)
    cid = s.arena.card_id
    assert marks[f"life-{cid}"][0] == after.event_count
    assert marks[f"card-{cid}"] == (after.event_count, "hit1")


def test_cues_are_deterministic_and_unique():
    s = start()
    a = act(ev.DAMAGE, replacement=3)
    one, two = fx.cues_for(a, s, apply(s, a)), fx.cues_for(a, s, apply(s, a))
    assert one == two
    ids = [c.id for c in one]
    assert len(ids) == len(set(ids))
    assert all(isinstance(c.to_dict()["params"], dict) for c in one)


def test_unrelated_actions_produce_no_cues():
    s = start()
    _, cues = step(s, ev.NOTE, text="hello")
    assert cues == []
    _, cues = step(s, ev.SPEED, value=3)
    assert cues == []
