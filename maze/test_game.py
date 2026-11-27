"""Game 상태 흐름 자동 테스트 (화면 없이): python maze/test_game.py"""
import os
import random
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(__file__))
from main import (Game, stage_params, PLAYER_STEP, GRACE, InputBuffer, KEY_DIRS, FINAL_STAGE, REF_PLAYER_STEP,
                  HUMAN_STEP, HUMAN_DELAY, slack_window, Item, item_kinds, RESPAWN_TIME, Mover, ARROW_PER_ITEM, ARROW_MAX, FIRE_COOLDOWN, PATROL_DETECT, PATROL_LOSE, PATROL_LEN, AMBUSH_AHEAD, ROLE_ORDER)
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


def test_chasers_do_not_start_bunched_up():
    """추격자들은 모두 서로 걸어서 경로 길이를 n등분한 만큼(최소 10칸) 떨어져 출발한다 (한 덩어리로 쫓지 않게)."""
    bad = total = 0
    for stage in (4, 7, 10, 13):
        for seed in range(30):
            g = Game(random.Random(seed * 3 + stage))
            g.stage = stage
            g.start_stage()
            n = len(g.chasers)
            need = max(10, int(0.7 * len(route_nodes(g.grid, (1, 1), g.exit)) / n))
            ok = True
            for i, a in enumerate(g.chasers[:-1]):
                reach = bfs_distances(g.grid, a.pos)
                ok &= all(reach[b.pos] >= need for b in g.chasers[i + 1:])
            total += 1
            bad += not ok
    print(f"  (붙어 시작한 판 {bad}/{total})")
    assert bad <= total * 0.05  # 드문 대비책 경우만 허용


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


def test_item_kinds_by_stage():
    assert item_kinds(1) == [] and item_kinds(2) == ["arrow"] and item_kinds(3) == ["arrow"]
    assert item_kinds(4) == ["arrow", "arrow"] and item_kinds(10) == ["arrow", "arrow"]


def test_arrow_item_pickup_adds_ammo_with_cap():
    g = make_corridor_game()
    g.items = [Item("arrow", (2, 1)), Item("arrow", (3, 1)), Item("arrow", (4, 1))]
    g.ammo = 0
    for _ in range(3):
        g.update(PLAYER_STEP + 0.01, RIGHT)
    assert g.items == []
    assert g.ammo == min(ARROW_MAX, 3 * ARROW_PER_ITEM)  # 먹은 만큼, 최대치에서 멈춤
    assert ARROW_PER_ITEM == 1                       # 아이템 하나 = 화살 한 발
    g2 = make_corridor_game()
    g2.items = [Item("arrow", (2, 1))]
    g2.ammo = 0
    g2.update(0.01, RIGHT)
    assert g2.ammo == ARROW_PER_ITEM


def test_leftover_arrows_do_not_carry_over_to_next_stage():
    g = Game(random.Random(1))
    g.state = "play"
    g.stage = 3
    g.start_stage()
    g.ammo = 3
    g.next_stage()
    assert g.ammo == 0 and g.arrows == []


def test_fire_needs_ammo_and_has_cooldown():
    g = make_corridor_game()
    g.ammo = 0
    assert g.fire() is False and g.arrows == []
    g.ammo = 2
    assert g.fire() is True and g.ammo == 1 and len(g.arrows) == 1
    assert g.fire() is False and g.ammo == 1          # 쿨다운 중
    g.update(FIRE_COOLDOWN + 0.01, None)
    assert g.fire() is True and g.ammo == 0


def test_arrow_kills_first_chaser_in_line_and_it_respawns():
    g = make_corridor_game()
    g.ammo = 1
    g.facing = RIGHT
    g.chasers = [Mover((4, 1)), Mover((3, 1))]       # 가까운 쪽(3,1)이 먼저 맞아야 한다
    g.respawns = []
    g.kills = 0
    g.fire()
    g.update(0.3, None)
    assert [c.pos for c in g.chasers] == [(4, 1)] and g.kills == 1
    assert g.arrows == [] and g.state == "play"
    assert g.respawns and abs(g.respawns[0] - RESPAWN_TIME) < 0.5
    for _ in range(int((RESPAWN_TIME + 0.5) * 60)):  # 시간이 지나면 다시 등장
        g.update(1 / 60, None)
        if g.state != "play":
            break
    assert len(g.chasers) == 2 or g.state != "play"


def test_arrow_stops_at_wall_and_misses_chaser_out_of_line():
    g = make_corridor_game()                          # (1,1)~(4,1) 가로 복도, (4,2),(4,3) 아래로
    g.ammo = 1
    g.facing = RIGHT
    g.chasers = [Mover((4, 3))]                       # 일직선이 아닌 곳
    g.fire()
    g.update(1.0, None)
    assert g.arrows == [] and len(g.chasers) == 1 and g.kills == 0


def test_arrow_flies_in_facing_direction_even_after_turning():
    g = make_corridor_game()
    g.player.pos = g.player.prev = (4, 1)
    g.ammo = 1
    g.face(DOWN)
    g.chasers = [Mover((4, 3))]
    g.fire()
    g.update(0.3, None)
    assert g.chasers == [] and g.kills == 1


def big_open_game(stage=5, seed=3):
    g = Game(random.Random(seed))
    g.stage = stage
    g.start_stage()
    g.state = "play"
    g.grace = 0.0
    return g


def test_chaser_count_and_roles_by_stage():
    expect = {1: 1, 2: 1, 3: 2, 5: 2, 6: 3, 8: 3, 9: 4, 10: 4}
    for stage, n in expect.items():
        g = big_open_game(stage)
        assert stage_params(stage)[2] == n and len(g.chasers) == n, stage
        assert [c.role for c in g.chasers] == [ROLE_ORDER[i % len(ROLE_ORDER)] for i in range(n)], stage
        for c in g.chasers:
            if c.role == "patrol":
                assert c.waypoints and PATROL_LEN[0] <= bfs_distances(g.grid, c.waypoints[0])[c.waypoints[1]] <= PATROL_LEN[1]


def test_ambusher_heads_for_the_tile_ahead_of_the_player():
    g = big_open_game(7)
    a = [c for c in g.chasers if c.role == "ambush"][0]
    ahead = astar(g.grid, g.player.pos, g.exit)
    target = ahead[AMBUSH_AHEAD]
    # 플레이어와 충분히 떨어진 상태에서는 목표 칸(앞쪽)으로 한 칸 가까워진다
    if len(astar(g.grid, a.pos, g.player.pos)) - 1 > 4 and a.pos != target:
        before = bfs_distances(g.grid, a.pos)[target]
        nxt = g.chaser_next_tile(a)
        assert nxt is not None and bfs_distances(g.grid, nxt)[target] == before - 1
    # 가까워지면 그냥 플레이어를 직접 쫓는다
    near = [q for q, d in bfs_distances(g.grid, a.pos).items() if d == 2][0]
    g.player.pos = g.player.prev = near
    direct = astar(g.grid, a.pos, near)[1]
    assert g.chaser_next_tile(a) == direct


def test_patroller_stays_on_its_route_while_player_is_far():
    g = big_open_game(6)
    p = g.chasers[1]
    g.chasers = [p]                                   # 순찰형만 두고
    far_player = max(bfs_distances(g.grid, p.pos).items(), key=lambda kv: kv[1])[0]
    g.player.pos = g.player.prev = far_player        # 플레이어는 아주 먼 곳
    route = set(astar(g.grid, p.waypoints[0], p.waypoints[1]))
    assert bfs_distances(g.grid, far_player)[p.pos] > PATROL_DETECT + 5
    for _ in range(int(25 * 60)):
        g.update(1 / 60, None)
        assert g.state == "play"
    assert not p.chasing and set(p.trail) <= route, "순찰 구간을 벗어났다"
    assert len(set(p.trail)) > 3, "제자리에 서 있었다"


def test_patroller_chases_when_player_is_near_and_gives_up_when_far():
    g = big_open_game(6)
    p = g.chasers[1]
    g.chasers = [p]
    a, b = p.waypoints
    # 순찰 경로 위에서 발견 거리 안쪽에 플레이어를 둔다
    near = [q for q, d in bfs_distances(g.grid, p.pos).items() if 3 <= d <= PATROL_DETECT]
    g.player.pos = g.player.prev = near[0]
    g.update(g.chaser_step + 0.01, None)
    assert p.chasing, "가까이 갔는데 쫓지 않는다"
    # 아주 멀리 가면 놓친다
    far = max(bfs_distances(g.grid, p.pos).items(), key=lambda kv: kv[1])[0]
    g.player.pos = g.player.prev = far
    assert bfs_distances(g.grid, far)[p.pos] > PATROL_LOSE
    g.update(g.chaser_step + 0.01, None)
    assert not p.chasing


def test_respawned_patroller_keeps_its_role():
    g = big_open_game(6)
    p = g.chasers[1]
    g.kill_chaser(p)
    assert g.respawn_roles == ["patrol"]
    g.update(RESPAWN_TIME + 0.1, None)
    assert any(c.role == "patrol" for c in g.chasers)


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
