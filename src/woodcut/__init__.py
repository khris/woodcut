#!/usr/bin/env python3
"""
목재 재단 최적화 - Guillotine Cut 시퀀스
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

    print("="*60)
    print("목재 재단 최적화 - Guillotine Cut")
    print("="*60)

    # 톱날 두께 (kerf) 입력
    kerf_input = input("톱날 두께 (kerf, mm, 기본값 5): ").strip()
    if kerf_input == "":
        kerf = 5
    else:
        try:
            kerf = int(kerf_input)
            if kerf <= 0:
                print("❌ 오류: 톱날 두께는 양수여야 합니다.")
                return
        except ValueError:
            print("❌ 오류: 숫자를 입력해주세요.")
            return
    print(f"✓ 톱날 두께: {kerf}mm")

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

    match strategy_choice:
        case "1":
            packer = AlignedFreeSpacePacker(PLATE_WIDTH, PLATE_HEIGHT, kerf, allow_rotation)
            strategy_name = "aligned_free_space"
            print("\n정렬 우선 자유 공간 전략 선택")
        case "2":
            packer = GeneticAlignedFreeSpacePacker(PLATE_WIDTH, PLATE_HEIGHT, kerf, allow_rotation)
            strategy_name = "genetic_aligned"
            print("\n유전 알고리즘 + AlignedFreeSpace 전략 선택")
        case "3":
            packer = BeamSearchPacker(PLATE_WIDTH, PLATE_HEIGHT, kerf, allow_rotation, beam_width=3)
            strategy_name = "beam_search"
            print("\nBeam Search 전략 선택 (beam_width=3)")
        case "4":
            packer = LookAheadPacker(PLATE_WIDTH, PLATE_HEIGHT, kerf, allow_rotation)
            strategy_name = "lookahead"
            print("\nLook-ahead 전략 선택")
        case "5":
            packer = GeneticGroupPreservingPacker(PLATE_WIDTH, PLATE_HEIGHT, kerf, allow_rotation)
            strategy_name = "genetic_group"
            print("\n그룹 보존 유전 알고리즘 전략 선택")
        case _:
            print(f"\n❌ 오류: 잘못된 선택 '{strategy_choice}'")
            print("1-5 사이의 숫자를 입력해주세요.")
            return

    # 패킹 실행
    plates = packer.pack(pieces)

    # 시각화
    visualize_solution(plates, pieces, PLATE_WIDTH, PLATE_HEIGHT, strategy_name)


if __name__ == "__main__":
    main()
