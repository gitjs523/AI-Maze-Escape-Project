"""스도쿠 - 3단계: 9x9 보드, 칸 선택과 숫자 입력, 중복 표시 (고정 퍼즐)."""
import tkinter as tk

from rules import find_conflicts

CELL = 56          # 칸 한 변(px)
MARGIN = 20        # 보드 바깥 여백
BOARD = CELL * 9   # 보드 한 변

# 임시 고정 퍼즐 (0 = 빈칸). 퍼즐 자동 생성은 2주차에 추가한다.
PUZZLE = [
    [5, 3, 0, 0, 7, 0, 0, 0, 0],
    [6, 0, 0, 1, 9, 5, 0, 0, 0],
    [0, 9, 8, 0, 0, 0, 0, 6, 0],
    [8, 0, 0, 0, 6, 0, 0, 0, 3],
    [4, 0, 0, 8, 0, 3, 0, 0, 1],
    [7, 0, 0, 0, 2, 0, 0, 0, 6],
    [0, 6, 0, 0, 0, 0, 2, 8, 0],
    [0, 0, 0, 4, 1, 9, 0, 0, 5],
    [0, 0, 0, 0, 8, 0, 0, 7, 9],
]


class SudokuApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("스도쿠")
        root.resizable(False, False)

        size = BOARD + MARGIN * 2
        self.canvas = tk.Canvas(root, width=size, height=size, bg="white", highlightthickness=0)
        self.canvas.pack()

        self.grid = [row[:] for row in PUZZLE]
        # 처음부터 있던 숫자(문제 숫자)는 수정할 수 없다
        self.fixed = [[v != 0 for v in row] for row in PUZZLE]
        self.sel = None  # 선택된 칸 (행, 열) 또는 None

        self.canvas.bind("<Button-1>", self.on_click)
        root.bind("<Key>", self.on_key)
        self.draw()

    # ---- 입력 처리 ----
    def on_click(self, event):
        col = (event.x - MARGIN) // CELL
        row = (event.y - MARGIN) // CELL
        if 0 <= row < 9 and 0 <= col < 9:
            self.sel = (row, col)
        else:
            self.sel = None  # 보드 바깥을 누르면 선택 해제
        self.draw()

    def on_key(self, event):
        if self.sel is None:
            return
        r, c = self.sel
        if event.keysym in ("Up", "Down", "Left", "Right"):
            dr, dc = {"Up": (-1, 0), "Down": (1, 0), "Left": (0, -1), "Right": (0, 1)}[event.keysym]
            self.sel = (min(8, max(0, r + dr)), min(8, max(0, c + dc)))
        elif not self.fixed[r][c]:
            if event.char in "123456789" and event.char != "":
                self.grid[r][c] = int(event.char)
            elif event.keysym in ("BackSpace", "Delete", "0"):
                self.grid[r][c] = 0
        self.draw()

    # ---- 그리기 ----
    def draw(self):
        c = self.canvas
        c.delete("all")
        # 3x3 구역을 번갈아 옅은 색으로 칠해 구역이 한눈에 보이게 한다
        for br in range(3):
            for bc in range(3):
                if (br + bc) % 2 == 0:
                    x0 = MARGIN + bc * CELL * 3
                    y0 = MARGIN + br * CELL * 3
                    c.create_rectangle(x0, y0, x0 + CELL * 3, y0 + CELL * 3, fill="#eef3fa", outline="")
        # 규칙 위반(같은 행·열·구역에 중복)인 칸은 옅은 빨강으로 칠한다
        conflicts = find_conflicts(self.grid)
        for r, col in conflicts:
            x0, y0 = MARGIN + col * CELL, MARGIN + r * CELL
            c.create_rectangle(x0, y0, x0 + CELL, y0 + CELL, fill="#fbd5d5", outline="")
        # 선택된 칸 강조
        if self.sel is not None:
            sr, sc = self.sel
            x0, y0 = MARGIN + sc * CELL, MARGIN + sr * CELL
            c.create_rectangle(x0, y0, x0 + CELL, y0 + CELL, fill="#ffe9a8", outline="")
        # 선: 3칸마다 굵게
        for i in range(10):
            w = 3 if i % 3 == 0 else 1
            pos = MARGIN + i * CELL
            c.create_line(MARGIN, pos, MARGIN + BOARD, pos, width=w, fill="#222")
            c.create_line(pos, MARGIN, pos, MARGIN + BOARD, width=w, fill="#222")
        # 숫자
        for r in range(9):
            for col in range(9):
                v = self.grid[r][col]
                if v:
                    c.create_text(
                        MARGIN + col * CELL + CELL // 2,
                        MARGIN + r * CELL + CELL // 2,
                        text=str(v), font=("맑은 고딕", 22, "bold"),
                        # 중복은 빨강, 문제 숫자는 검정, 내가 넣은 숫자는 파랑
                        fill="#d02020" if (r, col) in conflicts
                        else "#1b1b1b" if self.fixed[r][col] else "#1a5fd0",
                    )


def main():
    root = tk.Tk()
    SudokuApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
