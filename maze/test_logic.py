"""logic.py 자동 테스트: python maze/test_logic.py"""
import random
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from logic import generate_maze, astar, farthest_floor, neighbors, FLOOR, WALL


def reachable(grid, start):
    seen, stack = {start}, [start]
    while stack:
        for n in neighbors(grid, stack.pop()):
            if n not in seen:
                seen.add(n)
                stack.append(n)
    return seen


def test_connected_and_bordered():
    for seed in range(200):
        rng = random.Random(seed)
        cw, ch = rng.randint(3, 25), rng.randint(3, 18)
        g = generate_maze(cw, ch, rng)
        assert len(g) == 2 * ch + 1 and len(g[0]) == 2 * cw + 1
        floors = {(x, y) for y, r in enumerate(g) for x, v in enumerate(r) if v == FLOOR}
        assert reachable(g, (1, 1)) == floors, f"seed {seed}: 끊긴 길 있음"
        assert all(g[0][x] == WALL and g[-1][x] == WALL for x in range(len(g[0])))
        assert all(r[0] == WALL and r[-1] == WALL for r in g)


def test_astar_shortest_and_valid():
    for seed in range(100):
        rng = random.Random(seed)
        g = generate_maze(12, 9, rng)
        floors = [(x, y) for y, r in enumerate(g) for x, v in enumerate(r) if v == FLOOR]
        a, b = rng.choice(floors), rng.choice(floors)
        path = astar(g, a, b)
        assert path and path[0] == a and path[-1] == b
        assert all(abs(p[0]-q[0]) + abs(p[1]-q[1]) == 1 for p, q in zip(path, path[1:]))
        assert all(g[y][x] == FLOOR for x, y in path)
        # BFS 거리와 같아야 최단
        dist, frontier = {a: 0}, [a]
        while frontier:
            nxt = []
            for c in frontier:
                for n in neighbors(g, c):
                    if n not in dist:
                        dist[n] = dist[c] + 1
                        nxt.append(n)
            frontier = nxt
        assert len(path) - 1 == dist[b]


def test_astar_blocked_returns_none():
    g = [[1]*5, [1,0,1,0,1], [1]*5]
    assert astar(g, (1, 1), (3, 1)) is None
    assert astar(g, (1, 1), (1, 1)) == [(1, 1)]


def test_farthest_is_floor():
    g = generate_maze(10, 10, random.Random(1))
    f = farthest_floor(g, (1, 1))
    assert g[f[1]][f[0]] == FLOOR and f != (1, 1)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("통과:", name)
