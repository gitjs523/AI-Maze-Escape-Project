"""Game 상태 흐름 자동 테스트 (화면 없이): python maze/test_game.py"""
import os
import random
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(__file__))
from main import Game, stage_params
from logic import astar


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
