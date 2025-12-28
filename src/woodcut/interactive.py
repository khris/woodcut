#!/usr/bin/env python3
"""대화형 재단 최적화 CLI"""

from .strategies import RegionBasedPacker
from .visualizer import visualize_solution


def get_positive_int_input(prompt: str, default: int | None = None) -> int | None:
    """양수 정수 입력을 받는 헬퍼 함수

    Args:
        prompt: 사용자에게 보여줄 프롬프트 메시지
        default: 기본값 (None이면 필수 입력)

    Returns:
        입력받은 양수 정수, 또는 에러 시 None
    """
    user_input = input(prompt).strip()

    # 빈 입력 처리
    if user_input == "":
        if default is not None:
            return default
        print("❌ 오류: 값을 입력해주세요.")
        return None

    # 정수 변환 시도
    try:
        value = int(user_input)
        if value <= 0:
            print("❌ 오류: 양수를 입력해주세요.")
            return None
        return value
    except ValueError:
        print("❌ 오류: 숫자를 입력해주세요.")
        return None


def run_interactive():
    """대화형 CLI 실행"""
    pieces = [
        (800, 310, 2),
        (644, 310, 3),
        (371, 270, 4),
        (369, 640, 2),
    ]

    print("="*60)
    print("목재 재단 최적화 - Guillotine Cut")
    print("="*60)

    # 원판 크기 입력
    plate_width = get_positive_int_input("원판 너비 (mm, 기본값 2440): ", default=2440)
    if plate_width is None:
        return

    plate_height = get_positive_int_input("원판 높이 (mm, 기본값 1220): ", default=1220)
    if plate_height is None:
        return

    print(f"✓ 원판 크기: {plate_width}×{plate_height}mm")

    # 톱날 두께 입력
    kerf = get_positive_int_input("톱날 두께 (kerf, mm, 기본값 5): ", default=5)
    if kerf is None:
        return
    print(f"✓ 톱날 두께: {kerf}mm")

    # 회전 허용 여부
    rotation_input = input("조각 회전 허용? (y/n, 기본값 y): ").strip().lower() or "y"
    allow_rotation = rotation_input in ("y", "yes", "예", "")

    if allow_rotation:
        print("✓ 회전 허용 (결이 없는 재질)")
    else:
        print("✓ 회전 금지 (결이 있는 재질)")

    # 영역 기반 패킹 전략 사용
    packer = RegionBasedPacker(plate_width, plate_height, kerf, allow_rotation)
    strategy_name = "region_based"
    print("\n영역 기반 패킹 전략 사용")

    # 패킹 실행
    plates = packer.pack(pieces)

    # 시각화
    visualize_solution(plates, pieces, plate_width, plate_height, strategy_name)
