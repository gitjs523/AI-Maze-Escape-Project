"""Game 상태 흐름 자동 테스트 (화면 없이): python maze/test_game.py"""
import os
import random
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(__file__))
from main import (Game, stage_params, PLAYER_STEP, GRACE, InputBuffer, KEY_DIRS, FINAL_STAGE, REF_PLAYER_STEP,
                  HUMAN_STEP, HUMAN_DELAY, slack_window, Item, SPEED_TIME, SPEED_FACTOR, item_kinds, FREEZE_TIME, ITEM_TIME, POWER_TIME, RESPAWN_TIME, Mover)
import pygame
from logic import place_items, distances_from, bfs_distances, route_nodes, astar, safe_path_exists, shortest_routes_safe, route_slack, chaser_slack_map, generate_maze, farthest_floor


def run(game, policy, limit=120.0, dt=1 / 60):
    t = 0.0
    while game.state == "play" and t < limit:
        game.update(dt, policy(game))
        t += dt
    return t


def idle(game):
    return None


def walk_to_exit(game):
    path = astar(game.grid, game.player.pos, game.exit)
    if len(path) < 2:
        return None
    return (path[1][0] - path[0][0], path[1][1] - path[0][1])


def test_idle_player_gets_caught():
    for seed in range(20):
        g = Game(random.Random(seed))
        g.state = "play"
        run(g, idle)
        assert g.state == "over", f"seed {seed}"
        assert all(len(p) >= 1 for p in g.death_paths)


def test_chaser_never_starts_adjacent_or_on_solution():
    for seed in range(50):
        for stage in (1, 4, 8):
            g = Game(random.Random(seed))
            g.stage = stage
            g.start_stage()
            sol = set(astar(g.grid, (1, 1), g.exit))
            for c in g.chasers:
                assert c.pos not in sol and c.pos != g.exit


def test_runner_reaches_exit_or_is_caught_and_stage_advances():
    cleared = 0
    for seed in range(40):
        g = Game(random.Random(seed))
        g.state = "play"
        run(g, walk_to_exit)
        assert g.state in ("clear", "over")
        if g.state == "clear":
            cleared += 1
            g.next_stage()
            assert g.stage == 2 and g.state == "play"
    print(f"  (직진 로봇 1단계 탈출 {cleared}/40)")
    assert cleared > 0


def slack_of(g):
    return route_slack(g.grid, (1, 1), g.exit, [c.pos for c in g.chasers],
                       HUMAN_STEP, g.chaser_step, GRACE, HUMAN_DELAY)


def test_every_stage_is_fair_for_a_normal_human():
    """1~10단계 모두: 1.5초 뒤 출발, 칸당 0.14초로 최단 경로로 가는 사람이 잡히지 않는다(여유 >= 단계별 하한)."""
    too_tight = 0
    total = 0
    for stage in range(1, 11):
        lo, hi = slack_window(stage)
        for seed in range(40):
            g = Game(random.Random(seed * 5 + stage))
            g.stage = stage
            g.start_stage()
            total += 1
            if slack_of(g) < lo - 1e-9:
                too_tight += 1
    print(f"  (사람 기준으로 빠듯한 판 {too_tight}/{total})")
    assert too_tight == 0


def test_two_chasers_do_not_start_side_by_side():
    """추격자 2명은 걸어서 경로 길이의 35% 이상(최소 12칸) 떨어진 곳에서 출발해야 한다 (한 마리처럼 붙어 쫓지 않게)."""
    bad = total = 0
    for stage in (4, 7, 10, 13, 15):
        for seed in range(40):
            g = Game(random.Random(seed * 3 + stage))
            g.stage = stage
            g.start_stage()
            a, b = g.chasers[0].pos, g.chasers[1].pos
            need = max(12, int(0.35 * len(route_nodes(g.grid, (1, 1), g.exit))))
            total += 1
            bad += bfs_distances(g.grid, a)[b] < need
    print(f"  (붙어 시작한 판 {bad}/{total})")
    assert bad <= total * 0.03  # 드문 대비책 경우만 허용


def test_slack_map_matches_brute_force():
    rng = random.Random(7)
    for _ in range(25):
        g = generate_maze(rng.randint(5, 14), rng.randint(5, 10), rng)
        ex = farthest_floor(g, (1, 1))
        cs = rng.choice([0.3, 0.22, 0.16])
        smap, route = chaser_slack_map(g, (1, 1), ex, HUMAN_STEP, cs, GRACE, HUMAN_DELAY)
        off = [p for p in smap if p not in route]
        for p in rng.sample(off, min(4, len(off))):
            brute = route_slack(g, (1, 1), ex, [p], HUMAN_STEP, cs, GRACE, HUMAN_DELAY)
            assert abs(smap[p] - brute) < 1e-9, (p, smap[p], brute)


def test_difficulty_ramps_with_stage():
    """단계가 오를수록 사람 기준 여유가 줄어든다 (너무 쉬운 판이 후반에 나오지 않는다)."""
    import statistics
    med = {}
    for stage in (1, 4, 7, 10):
        vals = []
        for seed in range(30):
            g = Game(random.Random(seed))
            g.stage = stage
            g.start_stage()
            vals.append(slack_of(g))
        med[stage] = statistics.median(vals)
        lo, hi = slack_window(stage)
        assert max(vals) <= hi + 1e-9 + 1.0, (stage, max(vals), hi)  # 대비책이 쓰였을 때만 약간 넘을 수 있음
    print("  (여유 중앙값: " + ", ".join(f"{k}단계 {v:.1f}초" for k, v in med.items()) + ")")
    assert med[1] > med[4] > med[7] >= med[10] - 0.3


def test_safe_path_detects_blocked_corridor():
    # 일직선 복도: 추격자가 출구 쪽에 서 있으면 안전한 길이 없다
    g = [[1] * 12, [1] + [0] * 10 + [1], [1] * 12]
    assert safe_path_exists(g, (1, 1), (10, 1), [(5, 1)], 0.11, 0.3, 2.0) is False
    assert safe_path_exists(g, (1, 1), (10, 1), [(10, 1)], 0.11, 0.3, 2.0) is False


def make_corridor_game():
    """ㄱ자 복도: (1,1)에서 오른쪽으로 가다 (4,1)에서 아래로 꺾는다."""
    g = Game(random.Random(0))
    g.state = "play"
    g.grid = [[1] * 7, [1, 0, 0, 0, 0, 1, 1], [1, 1, 1, 1, 0, 1, 1], [1, 1, 1, 1, 0, 1, 1], [1] * 7]
    g.player.pos = g.player.prev = (1, 1)
    g.chasers = []
    g.exit = (4, 3)
    g.grace = 99
    g.player_timer = 0.0
    return g


RIGHT, DOWN = KEY_DIRS[pygame.K_RIGHT], KEY_DIRS[pygame.K_DOWN]


def test_blocked_turn_key_does_not_stop_player():
    """오른쪽으로 가는 중 아래 키를 미리 눌러도(아직 벽) 멈추지 않고 직진해야 한다."""
    g = make_corridor_game()
    g.update(0.2, [DOWN, RIGHT])
    assert g.player.pos == (2, 1), g.player.pos


def test_early_turn_is_remembered_and_executed_at_junction():
    g = make_corridor_game()
    buf = InputBuffer()
    held = {pygame.K_RIGHT: True, pygame.K_DOWN: False}
    buf.keydown(pygame.K_RIGHT)
    positions = []
    for i in range(40):
        if i == 12:  # 모퉁이보다 이른 시점(아직 아래는 벽)에 아래 키를 누르고 계속 누름
            buf.keydown(pygame.K_DOWN)
            held[pygame.K_DOWN] = True
        buf.tick(1 / 60)
        g.update(1 / 60, buf.candidates(held))
        buf.moved(g.last_move_dir)
        positions.append(g.player.pos)
        if g.state != "play":
            break
    assert g.state == "clear", positions[-1]


def test_tapped_turn_before_junction_is_not_lost():
    """모퉁이 직전에 아래 키를 톡 치고 바로 떼도 모퉁이에서 한 칸 꺾여야 한다."""
    g = make_corridor_game()
    buf = InputBuffer()
    held = {pygame.K_RIGHT: True, pygame.K_DOWN: False}
    buf.keydown(pygame.K_RIGHT)
    turned = False
    for i in range(40):
        if i == 12:
            buf.keydown(pygame.K_DOWN)  # 눌렀다가 바로 뗌 (held는 False 그대로)
        buf.tick(1 / 60)
        g.update(1 / 60, buf.candidates(held))
        buf.moved(g.last_move_dir)
        turned = turned or g.player.pos == (4, 2)
    assert turned


def test_no_keys_pressed_does_not_crash():
    """키를 아무것도 안 눌렀을 때(None, 빈 목록)도 안 죽어야 한다 — 시작 직후 실제로 발생한 버그."""
    for empty in (None, [], ()):
        g = make_corridor_game()
        g.update(0.5, empty)
        assert g.player.pos == (1, 1)
    # 실제 main 루프와 같은 방식: 제목 화면 → 시작 → 키 없이 진행
    buf = InputBuffer()
    g = Game(random.Random(1))
    g.update(1 / 60, buf.candidates({k: False for k in KEY_DIRS}))
    g.state = "play"
    for _ in range(300):
        buf.tick(1 / 60)
        g.update(1 / 60, buf.candidates({k: False for k in KEY_DIRS}))
        buf.moved(g.last_move_dir)


def test_buffered_turn_expires():
    buf = InputBuffer()
    buf.keydown(pygame.K_DOWN)
    buf.tick(0.35)
    assert buf.queued is None


def test_chaser_speed_scales_with_player_speed():
    """추격자는 플레이어보다 항상 일정 비율 이상 느려야 한다 (플레이어를 늦춰도 따돌릴 수 있는 정도 유지)."""
    for stage in (1, 5, 9, 15):
        ratio = stage_params(stage)[3] / PLAYER_STEP
        ref = max(0.15, 0.30 - 0.02 * (stage - 1)) / REF_PLAYER_STEP
        assert abs(ratio - ref) < 1e-9, (stage, ratio, ref)
    assert stage_params(FINAL_STAGE)[3] / PLAYER_STEP >= 1.3


def test_final_stage_ends_game_and_counts_total_time():
    g = Game(random.Random(2))
    g.state = "play"
    g.stage = FINAL_STAGE - 1
    g.start_stage()
    # 출구 바로 옆에 두고 한 칸 이동시켜 클리어
    g.chasers = []
    path = astar(g.grid, g.player.pos, g.exit)
    g.player.pos = g.player.prev = path[-2]
    g.elapsed = 12.5
    g.update(0.01, (path[-1][0] - path[-2][0], path[-1][1] - path[-2][1]))
    assert g.state == "clear" and abs(g.total_time - 12.51) < 1e-6
    g.next_stage()
    assert g.stage == FINAL_STAGE
    g.chasers = []
    path = astar(g.grid, g.player.pos, g.exit)
    g.player.pos = g.player.prev = path[-2]
    g.elapsed = 20.0
    g.update(0.01, (path[-1][0] - path[-2][0], path[-1][1] - path[-2][1]))
    assert g.state == "win", g.state
    assert abs(g.total_time - (12.51 + 20.01)) < 1e-6
    g.restart()
    assert g.stage == 1 and g.state == "play" and g.total_time == 0.0


def test_items_are_placed_on_valid_off_route_tiles():
    for stage in (1, 3, 6, 10):
        for seed in range(25):
            g = Game(random.Random(seed * 11 + stage))
            g.stage = stage
            g.start_stage()
            kinds = item_kinds(stage)
            assert sorted(i.kind for i in g.items) == sorted(kinds), (stage, seed)
            route = set(route_nodes(g.grid, (1, 1), g.exit))
            off = distances_from(g.grid, route)
            taken = [(1, 1), g.exit] + [c.pos for c in g.chasers]
            for it in g.items:
                assert g.grid[it.pos[1]][it.pos[0]] == 0          # 길 위
                assert it.pos not in taken and it.pos not in route  # 시작·출구·추격자·최단 경로와 안 겹침
                assert off[it.pos] >= 1                             # 돌아가야 먹을 수 있음
            assert len({i.pos for i in g.items}) == len(g.items)    # 서로 겹치지 않음


def test_speed_item_picked_up_speeds_player_and_expires():
    g = make_corridor_game()
    g.effects = {"speed": 0.0, "freeze": 0.0, "power": 0.0}
    g.items = [Item("speed", (2, 1))]
    assert abs(g.player_step() - PLAYER_STEP) < 1e-9
    g.update(0.01, RIGHT)
    assert g.player.pos == (2, 1) and g.items == []
    assert g.effects["speed"] > SPEED_TIME - 0.1
    assert abs(g.player_step() - PLAYER_STEP * SPEED_FACTOR) < 1e-9
    # 속도 증가 중에는 같은 시간에 더 많이 이동
    g2 = make_corridor_game()
    g2.effects = {"speed": 0.0, "freeze": 0.0, "power": 0.0}
    g.update(PLAYER_STEP * SPEED_FACTOR + 0.001, RIGHT)
    assert g.player.pos == (3, 1)                        # 짧아진 간격만에 한 칸 더 이동
    # 시간이 지나면 원래 속도
    for _ in range(int(SPEED_TIME * 60) + 5):
        g.update(1 / 60, None)
    assert g.effects["speed"] == 0.0 and abs(g.player_step() - PLAYER_STEP) < 1e-9


def test_freeze_item_stops_chasers_then_they_resume():
    g = Game(random.Random(1))
    g.state = "play"
    g.grace = 0.0
    g.effects["freeze"] = FREEZE_TIME
    before = [c.pos for c in g.chasers]
    for _ in range(int((FREEZE_TIME - 0.3) * 60)):
        g.update(1 / 60, None)
    assert [c.pos for c in g.chasers] == before, "멈춤 중인데 추격자가 움직였다"
    for _ in range(int(2.0 * 60)):  # 효과가 끝난 뒤 다시 쫓아와야 한다
        g.update(1 / 60, None)
    assert [c.pos for c in g.chasers] != before or g.state == "over"


def test_freeze_item_picked_up_sets_effect_and_stage_items():
    g = make_corridor_game()
    g.effects = {"speed": 0.0, "freeze": 0.0, "power": 0.0}
    g.items = [Item("freeze", (2, 1))]
    g.update(0.01, RIGHT)
    assert g.items == [] and g.effects["freeze"] > FREEZE_TIME - 0.1
    assert item_kinds(1) == ["speed"] and "freeze" in item_kinds(2) and "freeze" in item_kinds(10)


def test_power_kills_chaser_on_touch_and_it_respawns():
    g = make_corridor_game()
    g.effects = {"speed": 0.0, "freeze": 0.0, "power": POWER_TIME}
    g.respawns = []
    g.kills = 0
    g.player.pos = g.player.prev = (2, 1)
    g.chasers = [Mover((3, 1))]
    g.update(0.01, RIGHT)                       # 추격자가 서 있는 칸으로 이동
    assert g.state == "play" and g.chasers == [] and g.kills == 1
    assert g.respawns and abs(g.respawns[0] - RESPAWN_TIME) < 0.1
    for _ in range(int((RESPAWN_TIME + 0.5) * 60)):
        g.update(1 / 60, None)
        if g.state != "play":
            break
    assert len(g.chasers) == 1                  # 시간이 지나면 다시 등장


def test_touch_without_power_is_still_game_over():
    g = make_corridor_game()
    g.effects = {"speed": 0.0, "freeze": 0.0, "power": 0.0}
    g.respawns = []
    g.player.pos = g.player.prev = (2, 1)
    g.chasers = [Mover((3, 1))]
    g.update(0.01, RIGHT)
    assert g.state == "over"


def test_respawned_chaser_appears_far_from_player():
    g = Game(random.Random(5))
    g.stage = 6
    g.start_stage()
    g.state = "play"
    g.chasers.pop()
    g.respawns = [0.01]
    g.update(0.05, None)
    assert len(g.chasers) == len(set(c.pos for c in g.chasers)) == stage_params(6)[2]
    new = g.chasers[-1]
    assert bfs_distances(g.grid, g.player.pos)[new.pos] >= 20


def test_chasers_flee_during_power_and_never_approach():
    for seed in range(8):
        g = Game(random.Random(seed))
        g.stage = 5
        g.start_stage()
        g.state = "play"
        g.grace = 0.0
        g.effects["power"] = 4.0
        before = {id(c): bfs_distances(g.grid, g.player.pos)[c.pos] for c in g.chasers}
        for _ in range(int(3.5 * 60)):
            g.update(1 / 60, None)
            dist = bfs_distances(g.grid, g.player.pos)
            for c in g.chasers:
                assert dist[c.pos] >= before[id(c)], (seed, dist[c.pos], before[id(c)])
                before[id(c)] = dist[c.pos]


def test_power_item_exists_from_stage_3():
    assert "power" not in item_kinds(2) and "power" in item_kinds(3) and "power" in item_kinds(10)


def test_place_items_helper_basic():
    g = generate_maze(10, 8, random.Random(3))
    ex = farthest_floor(g, (1, 1))
    route = set(route_nodes(g, (1, 1), ex))
    picks = place_items(g, route, {(1, 1), ex}, ["speed", "freeze", "power"], random.Random(1))
    assert len(picks) == 3
    assert all(p not in route for _, p in picks)


def test_restart_resets():
    g = Game(random.Random(3))
    g.stage = 5
    g.restart()
    assert g.stage == 1 and g.state == "play"


def test_stage_params_grow_and_cap():
    assert stage_params(1)[3] > stage_params(6)[3]
    assert stage_params(99)[0] <= 28 and stage_params(99)[1] <= 18
    assert stage_params(1)[2] == 1 and stage_params(4)[2] == 2


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK:", name)
