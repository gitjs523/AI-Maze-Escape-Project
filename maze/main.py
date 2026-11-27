"""AI 추격 미로 탈출 — 2주차: 핵심 기능 (미로 생성, 이동, A* 추격자, 출구/게임 오버/다음 단계)."""
import os
import random
import sys

import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from logic import astar, bfs_distances, farthest_floor, generate_maze, is_floor, safe_path_exists, shortest_routes_safe

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

PLAYER_STEP = 0.11  # 플레이어가 한 칸 가는 시간(초)
GRACE = 2.0         # 단계 시작 후 추격자가 출발하기까지 (초)

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
    step = max(0.15, 0.30 - 0.02 * (stage - 1))
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


class Game:
    """게임 상태와 규칙. 화면이 없어도 update()로 돌릴 수 있다 (테스트용)."""

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.stage = 1
        self.state = "title"  # title / play / clear / over
        self.start_stage()

    def start_stage(self):
        """미로와 추격자 위치를 만든다. 잘 달리면 반드시 클리어할 수 있는 판만 통과시킨다."""
        cw, ch, n_chasers, self.chaser_step = stage_params(self.stage)
        start = (1, 1)
        picks = []
        for _ in range(60):  # 판 자체를 다시 만드는 횟수
            self.grid = generate_maze(cw, ch, self.rng)
            self.exit = farthest_floor(self.grid, start)
            dist = bfs_distances(self.grid, start)
            far = max(dist.values())
            solution = set(astar(self.grid, start, self.exit))
            # 시작점과 출구 사이 어딘가, 정답 길 위가 아닌 곳에서 출발
            spots = [p for p in dist if p not in solution and 0.3 * far <= dist[p] <= 0.9 * far]
            if len(spots) < n_chasers:
                continue
            for _ in range(40):  # 같은 미로에서 추격자 위치를 다시 뽑는 횟수
                picks = self.rng.sample(spots, n_chasers)
                args = (self.grid, start, self.exit, picks, PLAYER_STEP, self.chaser_step, GRACE)
                # 눈에 띄는 최단 경로로 가도 안전하고, 안전한 길도 있어야 통과
                if shortest_routes_safe(*args) and safe_path_exists(*args):
                    break
            else:
                continue
            break
        if len(picks) != n_chasers:  # 거의 없는 경우의 대비책: 출구에서 먼 칸 중에서 고름
            far_tiles = sorted((p for p in dist if p not in solution), key=lambda p: -dist[p])
            picks = far_tiles[:n_chasers]
        self.player = Mover(start)
        self.chasers = [Mover(p) for p in picks]
        self.player_timer = 0.0
        self.chaser_timer = 0.0
        self.grace = GRACE
        self.elapsed = 0.0
        self.death_paths = []

    def next_stage(self):
        self.stage += 1
        self.start_stage()
        self.state = "play"

    def restart(self):
        self.stage = 1
        self.start_stage()
        self.state = "play"

    def caught(self):
        return any(c.pos == self.player.pos for c in self.chasers)

    def update(self, dt, held_dir):
        """dt초 진행. held_dir은 이동을 시도할 방향 하나 또는 우선순위 목록 (없으면 None)."""
        self.last_move_dir = None
        if self.state != "play":
            return
        self.elapsed += dt
        for m in [self.player, *self.chasers]:
            m.t = min(1.0, m.t + dt / (PLAYER_STEP if m is self.player else self.chaser_step))

        # 플레이어 이동
        self.player_timer = max(0.0, self.player_timer - dt)
        if self.player_timer <= 0:
            # 우선순위 순서대로 갈 수 있는 첫 방향으로 이동 (막힌 방향은 건너뜀)
            if held_dir is None:
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
                self.player_timer = PLAYER_STEP
                self.last_move_dir = d
                if self.player.pos == self.exit:
                    self.state = "clear"
                    return
                if self.caught():
                    self.finish_caught()
                    return
                break

        # 추격자 이동 (출발 대기 후, 매 칸마다 A*로 최단 경로를 다시 계산)
        self.grace = max(0.0, self.grace - dt)
        if self.grace > 0:
            return
        self.chaser_timer -= dt
        while self.chaser_timer <= 0:
            self.chaser_timer += self.chaser_step
            for c in self.chasers:
                path = astar(self.grid, c.pos, self.player.pos)
                if path and len(path) > 1:
                    c.move_to(path[1])
            if self.caught():
                self.finish_caught()
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

        if g.state == "over":  # AI가 어떤 길로 쫓아왔는지 보여 준다
            for path in g.death_paths:
                if len(path) > 1:
                    pygame.draw.lines(s, PATH_C, False, [center(p) for p in path], max(2, ts // 6))

        r = ts * 0.36
        for c in g.chasers:
            pygame.draw.circle(s, CHASER_C, center(c.draw_pos()), r)
        pygame.draw.circle(s, PLAYER_C, center(g.player.draw_pos()), r)

        # 상단 정보줄
        pygame.draw.rect(s, (12, 14, 20), (0, 0, WIN_W, HUD_H))
        self.text(self.font, f"단계 {g.stage}", TEXT_C, (70, HUD_H // 2))
        self.text(self.font, f"{g.elapsed:5.1f}초", TEXT_C, (WIN_W - 70, HUD_H // 2))
        if g.state == "play":
            msg = f"추격자 출발까지 {g.grace:.1f}초" if g.grace > 0 else "도망쳐!"
            self.text(self.font, msg, CHASER_C if g.grace <= 0 else TEXT_C, (WIN_W // 2, HUD_H // 2))

        if g.state == "title":
            self.overlay()
            self.text(self.big, "AI 추격 미로 탈출", TEXT_C, (WIN_W // 2, 260))
            self.text(self.mid, "방향키로 이동해 초록색 출구까지 도망치세요", TEXT_C, (WIN_W // 2, 360))
            self.text(self.mid, "빨간 추격자는 벽을 돌아 최단 경로로 쫓아옵니다", CHASER_C, (WIN_W // 2, 405))
            self.text(self.font, "Enter 또는 스페이스: 시작", PATH_C, (WIN_W // 2, 500))
        elif g.state == "clear":
            self.overlay()
            self.text(self.big, f"단계 {g.stage} 탈출 성공!", EXIT_C, (WIN_W // 2, 300))
            self.text(self.font, "Enter: 다음 단계", TEXT_C, (WIN_W // 2, 400))
        elif g.state == "over":
            self.text(self.big, "잡혔다!", CHASER_C, (WIN_W // 2, 300))
            self.text(self.font, f"{g.stage}단계에서 종료  |  주황색 선: 추격자가 따라온 길", TEXT_C, (WIN_W // 2, 370))
            self.text(self.font, "R 또는 Enter: 1단계부터 다시", PATH_C, (WIN_W // 2, 410))

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
                    elif game.state == "over":
                        game.restart()
        buf.tick(dt)
        game.update(dt, buf.candidates(pygame.key.get_pressed()))
        buf.moved(game.last_move_dir)
        view.draw(game)
        pygame.display.flip()
    pygame.quit()


if __name__ == "__main__":
    main()
