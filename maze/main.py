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
EXIT_C = (90, 230, 130)
PATH_C = (255, 180, 80)
TEXT_C = (235, 238, 245)
ITEM_C = {"speed": (255, 220, 70), "freeze": (120, 230, 255), "power": (200, 120, 255)}

PLAYER_STEP = 0.13  # 플레이어가 한 칸 가는 시간(초). 시험 중: 이전 값 0.11(9.1칸/초) → 0.13(7.7칸/초)
GRACE = 2.0         # 단계 시작 후 추격자가 출발하기까지 (초)
FINAL_STAGE = 10    # 마지막 단계. 이 단계를 깨면 전체 클리어
SPEED_TIME = 4.0    # 속도 증가 아이템 효과 시간(초)
FREEZE_TIME = 3.0   # 추격자 멈춤 아이템 효과 시간(초)
POWER_TIME = 5.0    # 파워 아이템 효과 시간(초): 추격자가 도망가고, 닿으면 처치
RESPAWN_TIME = 8.0  # 처치된 추격자가 먼 곳에서 다시 나타나기까지(초)
ITEM_TIME = {"speed": SPEED_TIME, "freeze": FREEZE_TIME, "power": POWER_TIME}  # 종류별 효과 시간
SPEED_FACTOR = 0.6  # 속도 증가 중 칸당 시간 배율 (작을수록 빠름)
REF_PLAYER_STEP = 0.11  # 추격자 속도표를 만들 때 기준으로 삼은 플레이어 속도 (아래 stage_params 참고)

# 보통 사람 기준: 판을 보고 정하느라 1.5초 뒤에 움직이기 시작하고, 플레이어 최대 속도보다 조금 느리게(칸당 0.15초) 간다.
# 추격자 배치는 이 사람이 최단 경로로 가도 잡히지 않는 여유(초)를 단계별로 정해서 맞춘다.
HUMAN_DELAY = 1.5
HUMAN_STEP = 0.15


def item_kinds(stage):
    """단계별로 미로에 놓이는 아이템 종류. (아이템은 도움만 되므로 난이도 설계의 공평성 계산에는 영향이 없다.)"""
    kinds = ["speed"]
    if stage >= 2:
        kinds.append("freeze")
    if stage >= 3:
        kinds.append("power")
    return kinds


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

    def move_to(self, pos):
        self.prev, self.pos, self.t = self.pos, pos, 0.0
        self.trail.append(pos)

    def draw_pos(self):
        return (self.prev[0] + (self.pos[0] - self.prev[0]) * self.t,
                self.prev[1] + (self.pos[1] - self.prev[1]) * self.t)


class Item:
    """미로 위에 놓인 아이템. kind: speed(속도 증가) / freeze(추격자 멈춤) / power(추격자 처치)"""

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
        route_tiles = set(route)
        blocked = set(picks) | {start, self.exit}
        self.items = [Item(k, p) for k, p in
                      place_items(self.grid, route_tiles, blocked, item_kinds(self.stage), self.rng)]
        self.effects = {"speed": 0.0, "freeze": 0.0, "power": 0.0}  # 남은 효과 시간(초)
        self.respawns = []  # 처치된 추격자가 다시 나타나기까지 남은 시간(초) 목록
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
        self.start_stage()
        self.state = "play"

    def player_step(self):
        """지금 플레이어가 한 칸 가는 데 걸리는 시간 (속도 증가 중이면 짧아진다)."""
        return PLAYER_STEP * (SPEED_FACTOR if self.effects["speed"] > 0 else 1.0)

    def pickup(self):
        """플레이어가 서 있는 칸에 아이템이 있으면 먹고 효과를 켠다."""
        for it in list(self.items):
            if it.pos == self.player.pos:
                self.items.remove(it)
                self.effects[it.kind] = ITEM_TIME[it.kind]

    def caught(self):
        return any(c.pos == self.player.pos for c in self.chasers)

    def resolve_collisions(self):
        """플레이어와 추격자가 같은 칸이면: 파워 중에는 추격자 처치, 아니면 잡힘(게임 오버). 게임이 끝났으면 True."""
        hit = [c for c in self.chasers if c.pos == self.player.pos]
        if not hit:
            return False
        if self.effects["power"] > 0:
            for c in hit:
                self.chasers.remove(c)
                self.kills += 1
                self.respawns.append(RESPAWN_TIME)
            return False
        self.finish_caught()
        return True

    def spawn_chaser(self):
        """처치된 추격자를 플레이어에게서 먼 곳(걸어서 20칸 이상, 가능하면 미로의 먼 쪽)에 다시 내보낸다."""
        dist = bfs_distances(self.grid, self.player.pos)
        far = max(dist.values())
        cands = [p for p, d in dist.items() if d >= max(20, 0.4 * far) and p != self.exit]
        pos = self.rng.choice(cands) if cands else max(dist, key=dist.get)
        self.chasers.append(Mover(pos))

    def flee_step(self, pos, dist_from_player):
        """파워 중 추격자의 이동: 플레이어와 걸어서 가장 멀어지는 이웃 칸으로 (몰리면 제자리)."""
        here = dist_from_player.get(pos, 0)
        options = [n for n in neighbors(self.grid, pos) if dist_from_player.get(n, 0) > here]
        if not options:
            return None
        best = max(dist_from_player.get(n, 0) for n in options)
        return self.rng.choice([n for n in options if dist_from_player.get(n, 0) == best])

    def update(self, dt, held_dir):
        """dt초 진행. held_dir은 이동을 시도할 방향 하나 또는 우선순위 목록 (없으면 None)."""
        self.last_move_dir = None
        if self.state != "play":
            return
        self.elapsed += dt
        for k in self.effects:
            self.effects[k] = max(0.0, self.effects[k] - dt)
        for i in range(len(self.respawns) - 1, -1, -1):  # 처치된 추격자 재등장
            self.respawns[i] -= dt
            if self.respawns[i] <= 0:
                del self.respawns[i]
                self.spawn_chaser()
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
        if self.grace > 0 or self.effects["freeze"] > 0:  # 출발 전이거나 멈춤 아이템 효과 중이면 제자리
            return
        self.chaser_timer -= dt
        while self.chaser_timer <= 0:
            self.chaser_timer += self.chaser_step
            if self.effects["power"] > 0:  # 파워 중: 플레이어에게서 도망
                pd = bfs_distances(self.grid, self.player.pos)
                for c in self.chasers:
                    nxt = self.flee_step(c.pos, pd)
                    if nxt:
                        c.move_to(nxt)
            else:
                for c in self.chasers:
                    path = astar(self.grid, c.pos, self.player.pos)
                    if path and len(path) > 1:
                        c.move_to(path[1])
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
        frozen = g.effects["freeze"] > 0
        weak = g.effects["power"] > 0
        blink = weak and g.effects["power"] < 1.5 and int(g.effects["power"] * 6) % 2 == 0  # 끝나 가면 깜빡임
        for c in g.chasers:
            col = (255, 255, 255) if blink else ITEM_C["power"] if weak else ITEM_C["freeze"] if frozen else CHASER_C
            pygame.draw.circle(s, col, center(c.draw_pos()), r)
        for kind in ("speed", "power"):  # 효과 중: 플레이어 둘레에 아이템 색 고리
            if g.effects[kind] > 0:
                pygame.draw.circle(s, ITEM_C[kind], center(g.player.draw_pos()), r + max(2, ts // 6), max(2, ts // 8))
        pygame.draw.circle(s, PLAYER_C, center(g.player.draw_pos()), r)

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
            self.text(self.font, f"총 {FINAL_STAGE}단계 — 끝까지 탈출해 보세요", TEXT_C, (WIN_W // 2, 455))
            self.text(self.font, "Enter 또는 스페이스: 시작", PATH_C, (WIN_W // 2, 520))
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
        """아이템 도형: 속도=노란 번개 모양 삼각형, 멈춤=하늘색 마름모, 파워=보라색 별 모양 원."""
        s, col, r = self.screen, ITEM_C[kind], ts * 0.38
        if kind == "speed":
            pygame.draw.polygon(s, col, [(c[0] - r, c[1] + r), (c[0], c[1] - r), (c[0] + r, c[1] + r)])
        elif kind == "freeze":
            pygame.draw.polygon(s, col, [(c[0], c[1] - r), (c[0] + r, c[1]), (c[0], c[1] + r), (c[0] - r, c[1])])
        else:
            pygame.draw.circle(s, col, c, r)
            pygame.draw.circle(s, BG, c, r * 0.45)

    def draw_effects(self, g):
        """위쪽 정보줄 오른쪽(가운데 문구와 시간 표시 사이)에 켜진 효과와 남은 시간을 짧게 표시한다."""
        names = {"speed": "속도", "freeze": "멈춤", "power": "파워"}
        x = 615
        for kind in ("speed", "freeze", "power"):
            if g.effects[kind] > 0:
                self.text(self.font, f"{names[kind]} {g.effects[kind]:.1f}", ITEM_C[kind], (x + 38, HUD_H // 2))
                x += 95

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
