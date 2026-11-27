"""main() 루프 연기 테스트(화면 없이): 시작 → 키 없이 진행 → 방향키 입력 → 종료까지 예외가 없어야 한다.
사용: python -I maze/smoke_main.py"""
import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pygame
import main as game_main

pygame.init()
pygame.display.set_mode((10, 10))
post = lambda key: pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))
post(pygame.K_RETURN)                      # 시작: 이 직후 키 없이 진행하는 구간이 이번 오류 경로
pygame.time.set_timer(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT), 900)
pygame.time.set_timer(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN), 700)
pygame.time.set_timer(pygame.event.Event(pygame.QUIT), 4000, loops=1)
game_main.main()
print("OK: main() 루프 정상 종료")
