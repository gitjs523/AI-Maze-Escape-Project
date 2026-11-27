"""AI 추격 미로 탈출 — 2주차: 핵심 기능 (미로 생성, 이동, A* 추격자, 출구/게임 오버/다음 단계)."""
import os
import random
import sys

import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from logic import (astar, bfs_distances, chaser_slack_map, farthest_floor, generate_maze, is_floor,
                   neighbors, place_items)

WIN_W, WIN_H = 960, 720
HUD_H = 48

BG = (18, 20, 28)
WALL_C = (52, 58, 84)
FLOOR_C = (30, 34, 48)
PLAYER_C = (90, 200, 255)
CHASER_C = (255, 90, 90)
PATROL_C = (255, 160, 60)  # 순찰형 추격자(아직 플레이어를 못 찾았을 때)
EXIT_C = (90, 230, 130)
PATH_C = (255, 180, 80)
TEXT_C = (235, 238, 245)
ITEM_C = {"arrow": (255, 220, 70)}

PLAYER_STEP = 0.13  # 플레이어가 한 칸 가는 시간(초). 시험 중: 이전 값 0.11(9.1칸/초) → 0.13(7.7칸/초)
GRACE = 2.0         # 단계 시작 후 추격자가 출발하기까지 (초)
FINAL_STAGE = 10    # 마지막 단계. 이 단계를 깨면 전체 클리어
RESPAWN_TIME = 10.0  # 처치된 추격자가 먼 곳에서 다시 나타나기까지(초)
ARROW_SPEED = 18.0   # 화살이 날아가는 속도(칸/초)
ARROW_PER_ITEM = 2   # 화살 아이템 하나를 먹으면 얻는 화살 수
ARROW_MAX = 3        # 한 번에 들 수 있는 화살 수
FIRE_COOLDOWN = 0.4  # 발사 후 다음 발사까지(초)
PATROL_DETECT = 8    # 순찰형 추격자가 플레이어를 발견하는 거리(걸어서 칸 수)
PATROL_LOSE = 14     # 쫓다가 이 거리보다 멀어지면 놓치고 순찰로 돌아감
PATROL_LEN = (8, 14)  # 순찰 구간 길이(두 지점 사이 걸어서 칸 수)
REF_PLAYER_STEP = 0.11  # 추격자 속도표를 만들 때 기준으로 삼은 플레이어 속도 (아래 stage_params 참고)

# 보통 사람 기준: 판을 보고 정하느라 1.5초 뒤에 움직이기 시작하고, 플레이어 최대 속도보다 조금 느리게(칸당 0.15초) 간다.
# 추격자 배치는 이 사람이 최단 경로로 가도 잡히지 않는 여유(초)를 단계별로 정해서 맞춘다.
HUMAN_DELAY = 1.5
HUMAN_STEP = 0.15


def item_kinds(stage):
    """단계별로 미로에 놓이는 아이템. 1단계는 아이템 없이 달리기만, 2단계부터 화살, 4단계부터 화살 2개.
    (아이템은 도움만 되므로 난이도 설계의 공평성 계산에는 영향이 없다.)"""
    if stage < 2:
        return []
    return ["arrow"] if stage < 4 else ["arrow", "arrow"]


def slack_window(stage):
    """단계별 여유 시간 범위(초): 초반은 넉넉하게, 단계가 오를수록 빠듯하게 (최소 0.5초 여유는 유지)."""
    lo = max(0.5, 2.5 - 0.25 * (stage - 1))
    return lo, lo + 2.0

KEY_DIRS = {
    pygame.K_RIGHT: (1, 0), pygame.K_d: (1, 0),
    pygame.K_LEFT: (-1, 0), pygame.K_a: (-1, 0),
    pygame.K_DOWN: (0, 1), pygame.K_s: (0, 1),
    pygame.K_UP: (0, -1), pygame.K_w: (0, -1),
}


def stage_params(stage):
    """단계별 미로 크기, 추격자 수와 한 칸 이동 시간."""
    cw = min(8 + 2 * (stage - 1), 28)
    ch = min(6 + (stage - 1), 18)
    chasers = 1 if stage < 4 else 2
    # 추격자 속도는 플레이어 속도에 비례시킨다: 플레이어를 늦추거나 빠르게 해도
    # '추격자가 플레이어보다 몇 배 느린가'(따돌릴 수 있는 정도)는 그대로 유지된다.
    step = max(0.15, 0.30 - 0.02 * (stage - 1)) * PLAYER_STEP / REF_PLAYER_STEP
    return cw, ch, chasers, step


class Mover:
    """칸 단위로 움직이면서 화면에는 부드럽게 보이게 하는 이동 객체."""

    def __init__(self, pos):
        self.pos = pos
        self.prev = pos
        self.t = 1.0  # 0~1, 1이면 도착 완료
        self.trail = [pos]  # 지나온 칸 기록 (게임 오버 때 추격 경로로 보여 줌)
        self.role = "hunter"   # hunter: 항상 플레이어 위치를 알고 쫓음 / patrol: 구간을 순찰하다가 가까워지면 쫓음
        self.waypoints = None  # 순찰형: 순찰하는 두 지점
        self.widx = 1          # 순찰형: 지금 향하는 지점 번호
        self.chasing = False   # 순찰형: 플레이어를 쫓는 중인지

    def move_to(self, pos):
        self.prev, self.pos, self.t = self.pos, pos, 0.0
        self.trail.append(pos)

    def draw_pos(self):
        return (self.prev[0] + (self.pos[0] - self.prev[0]) * self.t,
                self.prev[1] + (self.pos[1] - self.prev[1]) * self.t)


class Item:
    """미로 위에 놓인 아이템. kind: arrow(화살 보급)"""

    def __init__(self, kind, pos):
        self.kind = kind
        self.pos = pos


class Game:
    """게임 상태와 규칙. 화면이 없어도 update()로 돌릴 수 있다 (테스트용)."""

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.stage = 1
        self.total_time = 0.0  # 지금까지 깬 단계들에 걸린 시간 합계
        self.kills = 0         # 이번 도전에서 처치한 추격자 수
        self.ammo = 0          # 가진 화살 수
        self.facing = (1, 0)   # 바라보는 방향 (화살이 나가는 방향)
        self.state = "title"  # title / play / clear / win / over
        self.start_stage()

    def start_stage(self):
        """미로와 추격자 위치를 만든다. 보통 사람이 최단 경로로 가도 잡히지 않되,
        단계가 오를수록 여유가 줄어들도록 추격자를 '여유 시간 범위'에 맞는 칸에 놓는다."""
        cw, ch, n_chasers, self.chaser_step = stage_params(self.stage)
        lo, hi = slack_window(self.stage)
        start = (1, 1)
        picks = []
        fallback = None
        for _ in range(60):  # 판 자체를 다시 만드는 횟수
            self.grid = generate_maze(cw, ch, self.rng)
            self.exit = farthest_floor(self.grid, start)
            slack, route = chaser_slack_map(self.grid, start, self.exit, HUMAN_STEP,
                                            self.chaser_step, GRACE, HUMAN_DELAY)
            off_route = [p for p in slack if p not in route]
            spots = [p for p in off_route if lo <= slack[p] <= hi]
            min_sep = max(12, int(0.35 * len(route)))  # 두 추격자는 경로 길이의 35% 이상 걸어야 만나는 곳에서 출발
            picks = self.pick_spread(spots, n_chasers, min_sep)
            if picks:
                break
            if fallback is None:  # 범위에 맞는 칸이 없을 때를 대비해 여유가 충분한 칸을 기억
                safe_enough = [p for p in off_route if slack[p] >= lo]
                fallback = self.pick_spread(safe_enough, n_chasers, min_sep // 2)
        if not picks:
            picks = fallback or sorted(off_route, key=lambda p: -slack[p])[:n_chasers]
        self.player = Mover(start)
        self.chasers = [Mover(p) for p in picks]
        for c in self.chasers[1:2]:  # 두 번째 추격자는 순찰형 (1명뿐인 단계는 사냥꾼만)
            self.make_patrol(c)
        route_tiles = set(route)
        blocked = set(picks) | {start, self.exit}
        self.items = [Item(k, p) for k, p in
                      place_items(self.grid, route_tiles, blocked, item_kinds(self.stage), self.rng)]
        self.arrows = []    # 날아가는 화살들
        self.fire_cd = 0.0  # 다음 발사까지 남은 시간
        self.facing = (1, 0)
        self.respawns = []  # 처치된 추격자가 다시 나타나기까지 남은 시간(초) 목록
        self.respawn_roles = []  # 위 목록과 같은 순서의 역할(되살아날 때 같은 역할로)
        self.player_timer = 0.0
        self.chaser_timer = 0.0
        self.grace = GRACE
        self.elapsed = 0.0
        self.death_paths = []

    def pick_spread(self, spots, n, min_sep):
        """spots에서 서로 '걸어서' min_sep칸 이상 떨어진 n곳을 무작위로 고른다 (없으면 빈 목록).
        화면상 거리가 아니라 걸어야 하는 거리를 쓴다: 벽 하나 사이로 가까워 보여도 길이 멀면 떨어진 것."""
        if len(spots) < n:
            return []
        for _ in range(40):
            picks = self.rng.sample(spots, n)
            if n == 1:
                return picks
            reach = bfs_distances(self.grid, picks[0])
            if all(reach.get(q, 1 << 30) >= min_sep for q in picks[1:]):
                return picks
        return []

    def next_stage(self):
        self.stage += 1
        self.start_stage()
        self.state = "play"

    def restart(self):
        self.stage = 1
        self.total_time = 0.0
        self.kills = 0
        self.ammo = 0
        self.start_stage()
        self.state = "play"

    def player_step(self):
        """플레이어가 한 칸 가는 데 걸리는 시간(초)."""
        return PLAYER_STEP

    def pickup(self):
        """플레이어가 서 있는 칸에 아이템이 있으면 먹는다."""
        for it in list(self.items):
            if it.pos == self.player.pos:
                self.items.remove(it)
                if it.kind == "arrow":
                    self.ammo = min(ARROW_MAX, self.ammo + ARROW_PER_ITEM)

    def face(self, d):
        """바라보는 방향을 바꾼다 (방향키를 누르면, 벽에 막혀 못 가더라도 그쪽을 본다)."""
        self.facing = d

    def fire(self):
        """바라보는 방향으로 화살을 쏜다. 쏘았으면 True."""
        if self.state != "play" or self.ammo <= 0 or self.fire_cd > 0:
            return False
        self.ammo -= 1
        self.fire_cd = FIRE_COOLDOWN
        px, py = self.player.pos
        self.arrows.append({"x": float(px), "y": float(py), "d": self.facing, "tile": (px, py)})
        return True

    def advance_arrows(self, dt):
        """화살을 날린다: 벽을 만나면 사라지고, 길에 있는 첫 추격자를 맞히면 그 추격자가 쓰러진다."""
        for a in list(self.arrows):
            dist = ARROW_SPEED * dt
            while dist > 0:
                step = min(0.25, dist)  # 작게 나눠 움직여 얇은 벽이나 추격자를 건너뛰지 않게 한다
                dist -= step
                a["x"] += a["d"][0] * step
                a["y"] += a["d"][1] * step
                tile = (int(round(a["x"])), int(round(a["y"])))
                if tile == a["tile"]:
                    continue
                a["tile"] = tile
                if not is_floor(self.grid, tile):
                    self.arrows.remove(a)
                    break
                hit = [c for c in self.chasers if c.pos == tile]
                if hit:
                    self.kill_chaser(hit[0])
                    self.arrows.remove(a)
                    break

    def make_patrol(self, c):
        """c를 순찰형으로 만든다: 지금 있는 곳과, 걸어서 8~14칸 떨어진 곳 사이를 오간다."""
        dist = bfs_distances(self.grid, c.pos)
        cands = [p for p, d in dist.items() if PATROL_LEN[0] <= d <= PATROL_LEN[1]]
        if not cands:
            return  # 너무 좁은 곳이면 사냥꾼으로 둔다
        c.role = "patrol"
        c.waypoints = (c.pos, self.rng.choice(cands))
        c.widx = 1
        c.chasing = False

    def kill_chaser(self, c):
        self.chasers.remove(c)
        self.kills += 1
        self.respawns.append(RESPAWN_TIME)
        self.respawn_roles.append(c.role)

    def chaser_next_tile(self, c):
        """추격자 c가 이번 칸에 갈 곳. 사냥꾼은 항상 플레이어 쪽 최단 경로, 순찰형은 순찰하다 발견하면 추격."""
        path = astar(self.grid, c.pos, self.player.pos)
        if c.role == "hunter":
            return path[1] if path and len(path) > 1 else None
        d = len(path) - 1 if path else 1 << 30
        if not c.chasing and d <= PATROL_DETECT:
            c.chasing = True
        elif c.chasing and d > PATROL_LOSE:
            c.chasing = False
            c.widx = 0 if c.waypoints[0] != c.pos else 1  # 놓치면 가까운 순찰 지점부터 다시
        if c.chasing:
            return path[1] if path and len(path) > 1 else None
        if c.pos == c.waypoints[c.widx]:
            c.widx ^= 1
        back = astar(self.grid, c.pos, c.waypoints[c.widx])
        return back[1] if back and len(back) > 1 else None

    def resolve_collisions(self):
        """플레이어와 추격자가 같은 칸이면 잡힘(게임 오버). 게임이 끝났으면 True."""
        if any(c.pos == self.player.pos for c in self.chasers):
            self.finish_caught()
            return True
        return False

    def spawn_chaser(self, role="hunter"):
        """처치된 추격자를 플레이어에게서 먼 곳(걸어서 20칸 이상, 가능하면 미로의 먼 쪽)에 다시 내보낸다."""
        dist = bfs_distances(self.grid, self.player.pos)
        far = max(dist.values())
        cands = [p for p, d in dist.items() if d >= max(20, 0.4 * far) and p != self.exit]
        pos = self.rng.choice(cands) if cands else max(dist, key=dist.get)
        c = Mover(pos)
        self.chasers.append(c)
        if role == "patrol":
            self.make_patrol(c)

    def update(self, dt, held_dir):
        """dt초 진행. held_dir은 이동을 시도할 방향 하나 또는 우선순위 목록 (없으면 None)."""
        self.last_move_dir = None
        if self.state != "play":
            return
        self.elapsed += dt
        self.fire_cd = max(0.0, self.fire_cd - dt)
        self.advance_arrows(dt)
        for i in range(len(self.respawns) - 1, -1, -1):  # 처치된 추격자 재등장
            self.respawns[i] -= dt
            if self.respawns[i] <= 0:
                del self.respawns[i]
                role = self.respawn_roles.pop(i) if i < len(self.respawn_roles) else "hunter"
                self.spawn_chaser(role)
        for m in [self.player, *self.chasers]:
            m.t = min(1.0, m.t + dt / (self.player_step() if m is self.player else self.chaser_step))

        # 플레이어 이동
        self.player_timer = max(0.0, self.player_timer - dt)
        if self.player_timer <= 0:
            # 우선순위 순서대로 갈 수 있는 첫 방향으로 이동 (막힌 방향은 건너뜀)
            if not held_dir:  # None 또는 빈 목록: 누른 키 없음
                dirs = []
            elif isinstance(held_dir[0], int):
                dirs = [held_dir]
            else:
                dirs = held_dir
            for d in dirs:
                nxt = (self.player.pos[0] + d[0], self.player.pos[1] + d[1])
                if not is_floor(self.grid, nxt):
                    continue
                self.player.move_to(nxt)
                self.pickup()
                self.player_timer = self.player_step()
                self.last_move_dir = d
                if self.player.pos == self.exit:
                    self.total_time += self.elapsed
                    self.state = "win" if self.stage >= FINAL_STAGE else "clear"
                    return
                if self.resolve_collisions():
                    return
                break

        # 추격자 이동 (출발 대기 후, 매 칸마다 A*로 최단 경로를 다시 계산)
        self.grace = max(0.0, self.grace - dt)
        if self.grace > 0:  # 출발 전에는 제자리
            return
        self.chaser_timer -= dt
        while self.chaser_timer <= 0:
            self.chaser_timer += self.chaser_step
            for c in self.chasers:
                nxt = self.chaser_next_tile(c)
                if nxt:
                    c.move_to(nxt)
            if self.resolve_collisions():
                return

    def finish_caught(self):
        self.state = "over"
        self.death_paths = [c.trail for c in self.chasers]


class View:
    def __init__(self, screen):
        self.screen = screen
        name = pygame.font.match_font("malgungothic,malgun gothic,applegothic,nanumgothic")
        self.font = pygame.font.Font(name, 22)
        self.big = pygame.font.Font(name, 56)
        self.mid = pygame.font.Font(name, 28)

    def text(self, font, msg, color, center):
        img = font.render(msg, True, color)
        self.screen.blit(img, img.get_rect(center=center))

    def draw(self, g):
        s = self.screen
        s.fill(BG)
        rows, cols = len(g.grid), len(g.grid[0])
        ts = min(WIN_W // cols, (WIN_H - HUD_H) // rows)
        ox = (WIN_W - ts * cols) // 2
        oy = HUD_H + (WIN_H - HUD_H - ts * rows) // 2

        def center(p):
            return (ox + (p[0] + 0.5) * ts, oy + (p[1] + 0.5) * ts)

        for y, row in enumerate(g.grid):
            for x, v in enumerate(row):
                pygame.draw.rect(s, WALL_C if v else FLOOR_C, (ox + x * ts, oy + y * ts, ts, ts))

        ex, ey = center(g.exit)
        pygame.draw.rect(s, EXIT_C, (ex - ts * 0.4, ey - ts * 0.4, ts * 0.8, ts * 0.8), border_radius=4)

        for it in g.items:
            self.draw_item(it.kind, center(it.pos), ts)

        if g.state == "over":  # AI가 어떤 길로 쫓아왔는지 보여 준다
            for path in g.death_paths:
                if len(path) > 1:
                    pygame.draw.lines(s, PATH_C, False, [center(p) for p in path], max(2, ts // 6))

        r = ts * 0.36
        for c in g.chasers:
            pygame.draw.circle(s, PATROL_C if c.role == "patrol" and not c.chasing else CHASER_C,
                               center(c.draw_pos()), r)
        pc = center(g.player.draw_pos())
        pygame.draw.circle(s, PLAYER_C, pc, r)
        if g.state == "play" and g.ammo > 0:  # 화살을 들고 있으면 바라보는 쪽에 조준점 표시
            fx, fy = g.facing
            pygame.draw.circle(s, ITEM_C["arrow"], (pc[0] + fx * ts * 0.55, pc[1] + fy * ts * 0.55), max(2, ts // 8))
        for a in g.arrows:  # 날아가는 화살
            c0 = center((a["x"], a["y"]))
            dx, dy = a["d"]
            pygame.draw.line(s, ITEM_C["arrow"], (c0[0] - dx * ts * 0.45, c0[1] - dy * ts * 0.45),
                             (c0[0] + dx * ts * 0.25, c0[1] + dy * ts * 0.25), max(2, ts // 6))

        # 상단 정보줄
        pygame.draw.rect(s, (12, 14, 20), (0, 0, WIN_W, HUD_H))
        self.text(self.font, f"단계 {g.stage}/{FINAL_STAGE}", TEXT_C, (90, HUD_H // 2))
        self.text(self.font, f"{g.elapsed:5.1f}초", TEXT_C, (WIN_W - 70, HUD_H // 2))
        if g.state == "play":
            msg = f"추격자 출발까지 {g.grace:.1f}초" if g.grace > 0 else "도망쳐!"
            self.text(self.font, msg, CHASER_C if g.grace <= 0 else TEXT_C, (WIN_W // 2, HUD_H // 2))
            self.draw_effects(g)

        if g.state == "title":
            self.overlay()
            self.text(self.big, "AI 추격 미로 탈출", TEXT_C, (WIN_W // 2, 260))
            self.text(self.mid, "방향키로 이동해 초록색 출구까지 도망치세요", TEXT_C, (WIN_W // 2, 360))
            self.text(self.mid, "빨간 추격자는 벽을 돌아 최단 경로로 쫓아옵니다", CHASER_C, (WIN_W // 2, 405))
            self.text(self.font, "노란 화살표를 먹으면 스페이스로 발사 — 맞은 추격자는 쓰러집니다", ITEM_C["arrow"], (WIN_W // 2, 450))
            self.text(self.font, f"총 {FINAL_STAGE}단계 — 끝까지 탈출해 보세요", TEXT_C, (WIN_W // 2, 495))
            self.text(self.font, "Enter 로 시작", PATH_C, (WIN_W // 2, 550))
        elif g.state == "clear":
            self.overlay()
            self.text(self.big, f"단계 {g.stage} 탈출 성공!", EXIT_C, (WIN_W // 2, 300))
            self.text(self.font, "Enter: 다음 단계", TEXT_C, (WIN_W // 2, 400))
        elif g.state == "win":
            self.overlay()
            self.text(self.big, "전체 탈출 성공!", EXIT_C, (WIN_W // 2, 280))
            self.text(self.mid, f"{FINAL_STAGE}개 단계를 모두 통과했습니다", TEXT_C, (WIN_W // 2, 365))
            self.text(self.mid, f"총 걸린 시간  {g.total_time:.1f}초", PATH_C, (WIN_W // 2, 415))
            self.text(self.font, "Enter 또는 스페이스: 처음부터 다시", TEXT_C, (WIN_W // 2, 500))
        elif g.state == "over":
            self.text(self.big, "잡혔다!", CHASER_C, (WIN_W // 2, 300))
            self.text(self.font, f"{g.stage}단계에서 종료  |  주황색 선: 추격자가 따라온 길", TEXT_C, (WIN_W // 2, 370))
            self.text(self.font, "R 또는 Enter: 1단계부터 다시", PATH_C, (WIN_W // 2, 410))

    def draw_item(self, kind, c, ts):
        """아이템 도형: 화살 = 노란 화살표(위쪽을 향한 삼각형 머리 + 몸통)."""
        s, col, r = self.screen, ITEM_C[kind], ts * 0.38
        pygame.draw.polygon(s, col, [(c[0], c[1] - r), (c[0] - r * 0.7, c[1] + r * 0.1), (c[0] + r * 0.7, c[1] + r * 0.1)])
        pygame.draw.rect(s, col, (c[0] - r * 0.18, c[1], r * 0.36, r))

    def draw_effects(self, g):
        """위쪽 정보줄에 가진 화살 수를 표시한다."""
        if g.ammo > 0:
            self.text(self.font, f"화살 {g.ammo}발", ITEM_C["arrow"], (700, HUD_H // 2))

    def overlay(self):
        dim = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        dim.fill((8, 10, 16, 190))
        self.screen.blit(dim, (0, 0))


class InputBuffer:
    """방향 입력 보관. 모퉁이 직전에 미리 누른 방향을 잠깐 기억했다가 갈 수 있게 되면 꺾는다."""

    TTL = 0.3  # 미리 누른 방향을 기억하는 시간(초)

    def __init__(self):
        self.order = []      # 방향키를 누른 순서
        self.queued = None   # 아직 못 쓴, 가장 최근에 누른 방향
        self.age = 0.0

    def keydown(self, key):
        self.order = [k for k in self.order if k != key] + [key]
        self.queued = KEY_DIRS[key]
        self.age = 0.0

    def tick(self, dt):
        self.age += dt
        if self.age > self.TTL:
            self.queued = None

    def candidates(self, pressed):
        """이동을 시도할 방향들 (우선순위 순): 미리 누른 방향 → 누르고 있는 키(최근 순)."""
        dirs = []
        if self.queued:
            dirs.append(self.queued)
        for k in reversed(self.order):
            if pressed[k] and KEY_DIRS[k] not in dirs:
                dirs.append(KEY_DIRS[k])
        return dirs

    def moved(self, d):
        """실제로 d 방향으로 움직였으면 미리 누른 입력은 사용된 것."""
        if d is not None and d == self.queued:
            self.queued = None


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("AI 추격 미로 탈출")
    clock = pygame.time.Clock()
    view = View(screen)
    game = Game()
    buf = InputBuffer()
    running = True
    while running:
        dt = min(clock.tick(60) / 1000.0, 0.1)
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key in KEY_DIRS:
                    buf.keydown(e.key)
                    game.face(KEY_DIRS[e.key])
                elif e.key in (pygame.K_SPACE, pygame.K_f) and game.state == "play":
                    game.fire()
                elif e.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_r):
                    if game.state == "title" and e.key != pygame.K_r:
                        game.state = "play"
                    elif game.state == "clear" and e.key != pygame.K_r:
                        game.next_stage()
                    elif game.state in ("over", "win"):
                        game.restart()
        buf.tick(dt)
        game.update(dt, buf.candidates(pygame.key.get_pressed()))
        buf.moved(game.last_move_dir)
        view.draw(game)
        pygame.display.flip()
    pygame.quit()


if __name__ == "__main__":
    main()
