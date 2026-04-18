#!/usr/bin/env python3
"""대화형 재단 최적화 CLI"""

from collections import Counter

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
    print("="*60)
    print("목재 재단 최적화 - Guillotine Cut")
    print("="*60)

    # 보유 원판 입력 받기
    print("\n[보유 원판 입력]")
    print("입력을 마치려면 너비에 '0' 또는 엔터를 입력하세요. (최소 1개)")
    stocks: list[tuple[int, int, int]] = []
    while True:
        idx = len(stocks) + 1
        w = get_positive_int_input(
            f"원판 {idx} 너비 (mm, 기본값 2440): ",
            default=2440 if idx == 1 else None,
        )
        if w is None or w == 0:
            if not stocks:
                print("❌ 오류: 최소 한 개의 원판은 입력해야 합니다.")
                continue
            break

        h = get_positive_int_input(
            f"원판 {idx} 높이 (mm, 기본값 1220): ",
            default=1220 if idx == 1 else None,
        )
        if h is None:
            print("❌ 높이 입력을 취소하고 다시 너비부터 입력합니다.")
            continue

        c = get_positive_int_input(
            f"원판 {idx} 수량 (장, 기본값 1): ", default=1
        )
        if c is None:
            c = 1

        stocks.append((w, h, c))
        print(f"  + 원판 추가: {w}×{h}mm, {c}장")

    total_plates = sum(s[2] for s in stocks)
    print(f"✓ 총 {len(stocks)}종류, {total_plates}장 원판 보유")

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

    # 조각 입력 받기
    print("\n[재단할 조각 입력]")
    print("입력을 마치려면 너비에 '0' 또는 엔터를 입력하세요.")
    pieces = []
    while True:
        idx = len(pieces) + 1
        w = get_positive_int_input(f"조각 {idx} 너비 (mm): ")
        if w is None or w == 0:
            if not pieces:
                print("❌ 오류: 최소 한 개의 조각은 입력해야 합니다.")
                continue
            break
        
        h = get_positive_int_input(f"조각 {idx} 높이 (mm): ")
        if h is None:
            print("❌ 높이 입력을 취소하고 다시 너비부터 입력합니다.")
            continue
            
        c = get_positive_int_input(f"조각 {idx} 수량 (개, 기본값 1): ", default=1)
        if c is None:
            c = 1
            
        pieces.append((w, h, c))
        print(f"  + 조각 추가: {w}x{h}mm, {c}개")

    packer = RegionBasedPacker(stocks, kerf, allow_rotation)
    strategy_name = "region_based"

    # 패킹 실행
    plates, unplaced = packer.pack(pieces)

    # 원판 재고 부족 경고
    if unplaced:
        counts = Counter((p['width'], p['height']) for p in unplaced)
        print(f"\n⚠️  원판 재고 부족: {len(unplaced)}개 조각 미배치")
        for (w, h), n in counts.items():
            print(f"   - {w}×{h}mm × {n}개")
        print("   → 원판 수량을 늘리거나 조각 크기를 확인하세요.")

    # 시각화
    visualize_solution(plates, pieces, strategy_name)
