"""스도쿠 - 1단계: 9x9 보드 화면 (고정 퍼즐 표시)."""
import tkinter as tk

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
        self.draw()

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
                        text=str(v), font=("맑은 고딕", 22, "bold"), fill="#1b1b1b",
                    )


def main():
    root = tk.Tk()
    SudokuApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
