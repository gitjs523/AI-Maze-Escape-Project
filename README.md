# AI 추격 미로 탈출

길을 찾아 쫓아오는 AI 추격자(A*)를 피해 미로의 출구까지 탈출하는 게임. (윈도우 단독 실행형 .exe)

- 인공지능 프로그래밍 프로젝트 (한세대학교 컴퓨터공학과, 오지성)
- Python + pygame-ce, PyInstaller로 .exe 빌드
- 기획서: `기획서/`, 주차별 인수인계 메모: `메모/`
- `sudoku/`: 중단된 첫 후보(스도쿠). 보존만 함

## 실행
```
python maze/main.py
```
방향키(또는 WASD)로 이동, 초록색 출구에 닿으면 다음 단계. Enter/스페이스로 시작·진행, R 다시 시작, Esc 종료.

## 테스트
```
python -I maze/test_logic.py
python -I maze/test_game.py
```
