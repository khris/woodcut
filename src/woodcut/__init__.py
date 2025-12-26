#!/usr/bin/env python3
"""
MDF 재단 최적화 - 실제 Guillotine Cut 시퀀스
- Guillotine Cut: 영역 전체를 관통
- 높이가 다르면 각 높이마다 절단선
- 분할된 영역 내에서만 절단
"""

from .strategies import (
    AlignedFreeSpacePacker,
    GeneticAlignedFreeSpacePacker,
    BeamSearchPacker,
    LookAheadPacker,
    GeneticGroupPreservingPacker,
)
from .visualizer import visualize_solution


def main():
    """CLI 엔트리 포인트"""
    pieces = [
        (800, 310, 2),
        (644, 310, 3),
        (371, 270, 4),
        (369, 640, 2),
    ]

    PLATE_WIDTH = 2440
    PLATE_HEIGHT = 1220
    KERF = 5

    print("="*60)
    print("MDF 재단 최적화 - 실제 Guillotine Cut")
    print("="*60)

    # 회전 허용 여부
    rotation_input = input("조각 회전 허용? (y/n, 기본값 y): ").strip().lower() or "y"
    allow_rotation = rotation_input in ("y", "yes", "예", "")

    if allow_rotation:
        print("✓ 회전 허용 (결이 없는 재질)")
    else:
        print("✓ 회전 금지 (결이 있는 재질)")

    # 전략 선택
    print("="*60)
    print("1. 정렬 우선 자유 공간 (그리디)")
    print("2. 유전 알고리즘 + AlignedFreeSpace")
    print("3. Beam Search (백트래킹)")
    print("4. Look-ahead (그룹화 휴리스틱)")
    print("5. 그룹 보존 유전 알고리즘 (추천)")
    print("="*60)

    strategy_choice = input("전략 선택 (1-5, 기본값 5): ").strip() or "5"

    if strategy_choice == "1":
        packer = AlignedFreeSpacePacker(PLATE_WIDTH, PLATE_HEIGHT, KERF, allow_rotation)
        print("\n정렬 우선 자유 공간 전략 선택")
    elif strategy_choice == "2":
        packer = GeneticAlignedFreeSpacePacker(PLATE_WIDTH, PLATE_HEIGHT, KERF, allow_rotation)
        print("\n유전 알고리즘 + AlignedFreeSpace 전략 선택")
    elif strategy_choice == "3":
        packer = BeamSearchPacker(PLATE_WIDTH, PLATE_HEIGHT, KERF, allow_rotation, beam_width=3)
        print("\nBeam Search 전략 선택 (beam_width=3)")
    elif strategy_choice == "4":
        packer = LookAheadPacker(PLATE_WIDTH, PLATE_HEIGHT, KERF, allow_rotation)
        print("\nLook-ahead 전략 선택")
    else:  # "5" or default
        packer = GeneticGroupPreservingPacker(PLATE_WIDTH, PLATE_HEIGHT, KERF, allow_rotation)
        print("\n그룹 보존 유전 알고리즘 전략 선택")

    # 패킹 실행
    plates = packer.pack(pieces)

    # 시각화
    visualize_solution(plates, pieces, PLATE_WIDTH, PLATE_HEIGHT)


if __name__ == "__main__":
    main()
