"""스도쿠 규칙 검사 (화면과 분리된 순수 로직)."""


def find_conflicts(grid):
    """같은 행·열·3x3 구역에 같은 숫자가 둘 이상 있는 칸의 (행, 열) 집합을 돌려준다."""
    conflicts = set()
    groups = []
    for i in range(9):
        groups.append([(i, c) for c in range(9)])  # 행
        groups.append([(r, i) for r in range(9)])  # 열
    for br in range(3):
        for bc in range(3):
            groups.append([(br * 3 + r, bc * 3 + c) for r in range(3) for c in range(3)])  # 구역

    for cells in groups:
        seen = {}
        for r, c in cells:
            v = grid[r][c]
            if v:
                seen.setdefault(v, []).append((r, c))
        for same in seen.values():
            if len(same) > 1:
                conflicts.update(same)
    return conflicts


def is_complete(grid):
    """모든 칸이 채워져 있고 규칙 위반이 없으면 True (= 퍼즐을 풀었다)."""
    return all(v != 0 for row in grid for v in row) and not find_conflicts(grid)


def peers(r, c):
    """(r, c)와 같은 행·열·3x3 구역에 있는 다른 칸들의 집합."""
    cells = {(r, i) for i in range(9)} | {(i, c) for i in range(9)}
    br, bc = r // 3 * 3, c // 3 * 3
    cells |= {(br + i, bc + j) for i in range(3) for j in range(3)}
    cells.discard((r, c))
    return cells
