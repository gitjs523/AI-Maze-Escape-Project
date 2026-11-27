"""미로 생성과 길찾기(A*) — 화면과 무관한 순수 로직 (테스트하기 쉽게 분리).

타일 격자: grid[y][x] == 1 이면 벽, 0 이면 길.
셀 w x h 개짜리 미로는 타일 (2w+1) x (2h+1) 이다.
"""
import heapq
import random

WALL = 1
FLOOR = 0
DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1)]


def generate_maze(cells_w, cells_h, rng=None):
    """DFS(재귀 백트래킹)로 미로를 만든다. 모든 길이 서로 연결되어 출구 도달이 보장된다.

    약간의 벽을 추가로 허물어 막다른 길만 있는 '완전 미로'보다 우회로가 생기게 한다
    (추격자를 따돌릴 여지가 있어야 게임이 되기 때문).
    """
    rng = rng or random
    w, h = 2 * cells_w + 1, 2 * cells_h + 1
    grid = [[WALL] * w for _ in range(h)]

    start = (1, 1)
    grid[1][1] = FLOOR
    stack = [start]
    while stack:
        x, y = stack[-1]
        options = []
        for dx, dy in DIRS:
            nx, ny = x + 2 * dx, y + 2 * dy
            if 0 < nx < w - 1 and 0 < ny < h - 1 and grid[ny][nx] == WALL:
                options.append((dx, dy))
        if not options:
            stack.pop()
            continue
        dx, dy = rng.choice(options)
        grid[y + dy][x + dx] = FLOOR
        grid[y + 2 * dy][x + 2 * dx] = FLOOR
        stack.append((x + 2 * dx, y + 2 * dy))

    # 우회로: 양옆이 길인 안쪽 벽을 일부 허문다
    candidates = []
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if grid[y][x] != WALL:
                continue
            horizontal = grid[y][x - 1] == FLOOR and grid[y][x + 1] == FLOOR
            vertical = grid[y - 1][x] == FLOOR and grid[y + 1][x] == FLOOR
            if horizontal != vertical:  # 기둥 모서리(둘 다 True/False)는 제외
                candidates.append((x, y))
    rng.shuffle(candidates)
    for x, y in candidates[: len(candidates) // 12]:
        grid[y][x] = FLOOR

    return grid


def is_floor(grid, pos):
    x, y = pos
    return 0 <= y < len(grid) and 0 <= x < len(grid[0]) and grid[y][x] == FLOOR


def neighbors(grid, pos):
    x, y = pos
    for dx, dy in DIRS:
        n = (x + dx, y + dy)
        if is_floor(grid, n):
            yield n


def astar(grid, start, goal):
    """A* 최단 경로. start부터 goal까지 좌표 리스트(양끝 포함)를 돌려주고, 길이 없으면 None."""
    if start == goal:
        return [start]
    counter = 0  # 우선순위가 같을 때 비교 오류 방지용 순번
    open_heap = [(0, counter, start)]
    came_from = {start: None}
    g_cost = {start: 0}
    while open_heap:
        _, _, cur = heapq.heappop(open_heap)
        if cur == goal:
            path = []
            while cur is not None:
                path.append(cur)
                cur = came_from[cur]
            path.reverse()
            return path
        for nxt in neighbors(grid, cur):
            ng = g_cost[cur] + 1
            if ng < g_cost.get(nxt, 1 << 30):
                g_cost[nxt] = ng
                came_from[nxt] = cur
                counter += 1
                h = abs(nxt[0] - goal[0]) + abs(nxt[1] - goal[1])  # 맨해튼 거리
                heapq.heappush(open_heap, (ng + h, counter, nxt))
    return None


def bfs_distances(grid, origin):
    """origin에서 모든 길 칸까지의 걸음 수 {좌표: 거리}."""
    from collections import deque

    dist = {origin: 0}
    queue = deque([origin])
    while queue:
        cur = queue.popleft()
        for nxt in neighbors(grid, cur):
            if nxt not in dist:
                dist[nxt] = dist[cur] + 1
                queue.append(nxt)
    return dist


def farthest_floor(grid, origin):
    """origin에서 걸어서 가장 먼 길 칸. 출구 위치를 정할 때 쓴다."""
    dist = bfs_distances(grid, origin)
    return max(dist, key=dist.get)


def safe_path_exists(grid, start, goal, chaser_positions, player_step, chaser_step, grace, margin=2):
    """출구까지 '모든 칸에 추격자보다 margin칸 이상 먼저 도착'하는 길이 있는가.

    추격자는 grace초 뒤 출발해서 칸당 chaser_step초로 최단 경로를 따라온다고 보고,
    플레이어는 칸당 player_step초로 달린다고 본다. 이 조건을 만족하면 가만히 달리기만 해도
    클리어할 수 있으므로 '공평한 판'으로 쓸 수 있다.
    """
    from collections import deque

    dists = [bfs_distances(grid, c) for c in chaser_positions]

    blocked = set(chaser_positions)  # 출발 대기 중에도 추격자는 그 칸에 서 있다 (닿으면 잡힘)

    def ok(node, steps):
        if node in blocked:
            return False
        t = steps * player_step
        return all(t + margin * chaser_step < grace + (d.get(node, 1 << 30) - 1) * chaser_step
                   for d in dists)

    if not ok(start, 0):
        return False
    seen = {start: 0}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        if cur == goal:
            return True
        for nxt in neighbors(grid, cur):
            if nxt not in seen and ok(nxt, seen[cur] + 1):
                seen[nxt] = seen[cur] + 1
                queue.append(nxt)
    return False


def shortest_routes_safe(grid, start, goal, chaser_positions, player_step, chaser_step, grace, margin=2):
    """출구까지의 최단 경로 위에 있는 모든 칸이 안전한가.

    사람은 눈에 띄는 가장 짧은 길로 가기 쉽다. 그 길로 가도 추격자보다 먼저 지나갈 수 있어야
    '돌아가야만 사는 판'이 되지 않는다.
    """
    d_start = bfs_distances(grid, start)
    d_goal = bfs_distances(grid, goal)
    total = d_start[goal]
    dists = [bfs_distances(grid, c) for c in chaser_positions]
    blocked = set(chaser_positions)
    for node, steps in d_start.items():
        if steps + d_goal[node] != total:  # 최단 경로 위의 칸만 본다
            continue
        if node in blocked:
            return False
        t = steps * player_step
        for d in dists:
            if not t + margin * chaser_step < grace + (d.get(node, 1 << 30) - 1) * chaser_step:
                return False
    return True
