from finaltitan import events as ev
from finaltitan.catalog import load_catalog
from finaltitan.combat import damage_pipeline, prevention
from finaltitan.engine import initial_state, reduce
from finaltitan.events import act
from finaltitan.guide import LEVELS, GuidanceSettings, guide
from finaltitan.setup import GameSetup, build_enemy, load_presets

CAT = load_catalog()


def make_setup(players=1, difficulty="Easy", seed=3, preset=None):
    s = GameSetup(players=players, difficulty=difficulty, seed=seed, preset=preset)
    s.player_titans = [t.id for t in CAT.titans.values() if t.enemy_usable][:3 * players]
    build_enemy(s, CAT, load_presets())
    return s


def run(setup, *actions):
    return reduce(initial_state(setup, CAT), [act(ev.BEGIN_GAME), *actions])


ENEMY_TURN = (act(ev.SET_STARTER, side="enemy"), act(ev.START_TURN))


def test_levels_are_beginner_and_expert():
    assert LEVELS == ["Beginner", "Expert"]


def test_catalog_only_has_cards_with_images():
    assert CAT.titans and all(t.image for t in CAT.titans.values())
    assert all(u.image for u in CAT.upgrades.values())


def test_enemy_deck_excludes_player_titans_and_unusable():
    s = make_setup(players=2, difficulty="Hard")
    assert len(s.enemy_titans) == 6 and len(s.enemy_upgrades) == 6
    assert not set(s.enemy_titans) & s.drafted()
    assert all(CAT.titans[t].enemy_usable for t in s.enemy_titans)


def test_every_titan_appears_only_once_across_the_game():
    for seed in range(1, 15):
        s = make_setup(players=3, difficulty="Insane", seed=seed)
        assert len(set(s.enemy_titans)) == len(s.enemy_titans)
        assert len(set(s.player_titans)) == len(s.player_titans)
        assert not set(s.enemy_titans) & set(s.player_titans)
        assert len(set(s.enemy_upgrades)) == len(s.enemy_upgrades)


def test_seed_is_deterministic():
    assert make_setup(seed=5).enemy_titans == make_setup(seed=5).enemy_titans


def test_first_steps_preset_order():
    s = make_setup(preset="first_steps")
    assert [CAT.titans[t].name for t in s.enemy_titans] == ["Crimson Knight", "Impulse", "Final Boss"]


def test_begin_game_reveals_each_card_once():
    st = run(make_setup())
    assert st.arena and st.arena.life == st.arena.max_life and st.enemy_role == "champion"
    assert len(st.bench) == 1 and len(st.active_upgrades) == 1 and st.phase == "fight_start"
    keys = [(r.kind, r.card_id) for r in st.last_reveals]
    assert len(keys) == len(set(keys)) == 3


def test_next_enemy_reveal_after_fight_is_unique():
    s = make_setup(difficulty="Standard")
    st = run(s, act(ev.SET_STARTER, side="players"), act(ev.FIGHT_END, reason="enemy_defeated"), act(ev.ADVANCE_FIGHT))
    keys = [(r.kind, r.card_id) for r in st.last_reveals]
    assert len(keys) == len(set(keys))


def test_turns_alternate_without_die_input():
    s = make_setup()
    st = run(s, *ENEMY_TURN)
    assert st.active_side == "enemy" and st.turn_started
    st = run(s, *ENEMY_TURN, act(ev.END_TURN))
    assert st.active_side == "players" and st.turn_started
    st = run(s, *ENEMY_TURN, act(ev.END_TURN), act(ev.END_TURN))
    assert st.active_side == "enemy" and not st.turn_started


def test_charge_flag_toggles():
    s = make_setup()
    tid = run(s).arena.card_id
    assert run(s, act(ev.FLAG, target=tid, flag="charged", value=True)).arena.charged
    assert not run(s, act(ev.FLAG, target=tid, flag="charged", value=True),
                   act(ev.FLAG, target=tid, flag="charged", value=False)).arena.charged


def test_blessed_and_cursed_exclude_each_other():
    s = make_setup()
    tid = run(s).arena.card_id
    st = run(s, act(ev.TOKEN, target=tid, token="blessed", delta=1), act(ev.TOKEN, target=tid, token="cursed", delta=1))
    assert st.arena.statuses.blessed_cursed == "none"


def test_damage_pipeline():
    c = damage_pipeline(base=3, power=1, bonus=0, cancel=False, armor=2, replacement=None)
    assert (c.increased, c.final) == (4, 2)
    assert prevention(2, 5, 1, 1) == (0, "dodge")
    assert prevention(5, 5, 0, 1) == (0, "minion")
    assert prevention(4, 5, 0, 1) == (4, None)


def test_damage_applies_armor_and_defeats():
    s = make_setup()
    st = run(s)
    tid, life = st.arena.card_id, st.arena.max_life
    st = run(s, act(ev.TOKEN, target=tid, token="armor", delta=1), act(ev.SET_STARTER, side="players"), act(ev.DAMAGE, base=3))
    assert st.arena.life == life - max(3 - (CAT.titans[tid].armor + 1), 0)
    st = run(s, act(ev.SET_STARTER, side="players"), act(ev.DAMAGE, base=99))
    assert st.phase == "cleanup" and st.result.reason == "enemy_defeated" and st.arena is None


def test_enemy_defeated_next_enters_as_challenger():
    s = make_setup()
    st = run(s, act(ev.SET_STARTER, side="players"), act(ev.FIGHT_END, reason="enemy_defeated"), act(ev.ADVANCE_FIGHT))
    assert st.phase == "fight_start" and st.enemy_role == "challenger" and st.fight_no == 2
    assert len(st.defeated) == 1 and len(st.active_upgrades) >= 2


def test_player_defeated_enemy_stays_champion():
    s = make_setup()
    st = run(s, act(ev.SET_STARTER, side="enemy"), act(ev.FIGHT_END, reason="player_defeated"), act(ev.ADVANCE_FIGHT))
    assert st.enemy_role == "champion" and st.player_titans_left == 2 and st.phase == "fight_start"


def test_victory():
    s = make_setup()
    actions = []
    for _ in range(s.enemy_count()):
        actions += [act(ev.SET_STARTER, side="players"), act(ev.FIGHT_END, reason="enemy_defeated"), act(ev.ADVANCE_FIGHT)]
    assert run(s, *actions).phase == "victory"


def test_defeat():
    s = make_setup()
    actions = []
    for _ in range(3):
        actions += [act(ev.SET_STARTER, side="enemy"), act(ev.FIGHT_END, reason="player_defeated"), act(ev.ADVANCE_FIGHT)]
    assert run(s, *actions).phase == "defeat"


def test_enemy_returned_skips_upgrade_and_fights_next():
    s = make_setup(difficulty="Standard")
    st = run(s)
    eid, hand = st.arena.card_id, len(st.upgrade_hand)
    st = run(s, act(ev.SET_STARTER, side="players"), act(ev.FIGHT_END, reason="enemy_returned"), act(ev.ADVANCE_FIGHT))
    assert len(st.upgrade_hand) == hand and st.arena.card_id == eid and st.enemy_role == "challenger"
    assert st.arena.life == st.arena.max_life


def test_final_fight_reveals_all_upgrades():
    s = make_setup(difficulty="Standard")  # 3 enemies
    st = run(s, act(ev.SET_STARTER, side="players"), act(ev.FIGHT_END, reason="enemy_defeated"), act(ev.ADVANCE_FIGHT),
             act(ev.SET_STARTER, side="players"), act(ev.FIGHT_END, reason="enemy_defeated"), act(ev.ADVANCE_FIGHT))
    assert st.enemy_remaining() == 1 and not st.upgrade_hand


def test_poison_and_fire_tick():
    s = make_setup()
    tid = run(s).arena.card_id
    st = run(s, act(ev.TOKEN, target=tid, token="poison", delta=2), act(ev.TOKEN, target=tid, token="fire", delta=1), *ENEMY_TURN)
    assert st.arena.life == st.arena.max_life - 3 and st.arena.statuses.fire == 2


def test_expert_guide_omits_redundant_enemy_turn_start_text():
    state = run(make_setup(), act(ev.SET_STARTER, side="enemy"))
    expert = guide(state, GuidanceSettings(level="Expert"))
    assert expert.step == "enemy_turn_start"
    assert expert.lines == []
    assert [(action.label, action.kind) for action in expert.primary] == [("Start enemy turn", ev.START_TURN)]

    beginner = guide(state, GuidanceSettings(level="Beginner"))
    assert any("start-of-turn abilities" in line for line in beginner.lines)
    assert beginner.primary == expert.primary


def test_expert_guide_omits_enemy_roll_text():
    state = run(make_setup(), *ENEMY_TURN)
    expert = guide(state, GuidanceSettings(level="Expert"))
    assert expert.step == "enemy_turn"
    assert expert.lines == []
    assert [(action.label, action.kind) for action in expert.primary] == [("End enemy turn", ev.END_TURN)]

    beginner = guide(state, GuidanceSettings(level="Beginner"))
    assert any("roll one die" in line for line in beginner.lines)
    assert beginner.primary == expert.primary


def test_expert_guide_omits_players_turn_text():
    state = run(make_setup(), act(ev.SET_STARTER, side="players"))
    expert = guide(state, GuidanceSettings(level="Expert"))
    assert expert.step == "players_turn"
    assert expert.lines == []
    assert [(action.label, action.kind) for action in expert.primary] == [("End our turn", ev.END_TURN)]

    beginner = guide(state, GuidanceSettings(level="Beginner"))
    assert any("Enter everything that affects the enemy" in line for line in beginner.lines)
    assert beginner.primary == expert.primary


def test_guide_covers_every_step_and_level():
    s = make_setup()
    flows = [
        [*ENEMY_TURN, act(ev.END_TURN), act(ev.END_TURN), act(ev.FIGHT_END, reason="enemy_defeated"), act(ev.ADVANCE_FIGHT)],
        [act(ev.SET_STARTER, side="enemy"), act(ev.FIGHT_END, reason="player_returned")],
        [act(ev.SET_STARTER, side="enemy"), act(ev.FIGHT_END, reason="both_defeated")],
        [act(ev.SET_STARTER, side="enemy"), act(ev.FIGHT_END, reason="enemy_returned")],
    ]
    init = initial_state(s, CAT)
    for flow in flows:
        full = [act(ev.BEGIN_GAME), *flow]
        for n in range(len(full) + 1):
            st = reduce(init, full[:n])
            for level in LEVELS:
                g = guide(st, GuidanceSettings(level=level))
                assert g.step and (g.lines or g.primary)
                if g.confirms:
                    assert len(g.confirms) == len(g.lines) - 1, g.step
                if level == "Expert":
                    assert len(g.lines) <= 1 and not g.hints
