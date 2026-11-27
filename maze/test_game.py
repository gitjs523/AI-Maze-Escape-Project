"""Game 상태 흐름 자동 테스트 (화면 없이): python maze/test_game.py"""
import os
import random
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(__file__))
from main import Game, stage_params, PLAYER_STEP, GRACE, InputBuffer, KEY_DIRS
import pygame
from logic import astar, safe_path_exists, shortest_routes_safe


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


def test_every_stage_is_fair():
    """1~10단계, 여러 판 모두에서 추격자보다 먼저 도착하는 안전한 길이 있어야 한다."""
    bad = 0
    total = 0
    for stage in range(1, 11):
        for seed in range(60):
            g = Game(random.Random(seed * 7 + stage))
            g.stage = stage
            g.start_stage()
            total += 1
            args = (g.grid, (1, 1), g.exit, [c.pos for c in g.chasers], PLAYER_STEP, g.chaser_step, GRACE)
            if not (safe_path_exists(*args) and shortest_routes_safe(*args)):
                bad += 1
    print(f"  (불공평한 판 {bad}/{total})")
    assert bad == 0


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


def test_buffered_turn_expires():
    buf = InputBuffer()
    buf.keydown(pygame.K_DOWN)
    buf.tick(0.35)
    assert buf.queued is None


def test_restart_resets():
    g = Game(random.Random(3))
    g.stage = 5
    g.restart()
    assert g.stage == 1 and g.state == "play"


def test_stage_params_grow_and_cap():
    assert stage_params(1)[3] > stage_params(6)[3] >= 0.15
    assert stage_params(99)[0] <= 28 and stage_params(99)[1] <= 18
    assert stage_params(1)[2] == 1 and stage_params(4)[2] == 2


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK:", name)
