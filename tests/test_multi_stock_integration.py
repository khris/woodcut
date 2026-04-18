"""멀티 stock 통합 테스트 — 회귀/신규/편향/엣지."""
import pytest

from woodcut.strategies.region_based import RegionBasedPacker


HYUPTAG_PIECES = [
    (560, 350, 2),
    (446, 50, 2),
    (369, 50, 2),
    (550, 450, 1),
    (450, 100, 1),
    (450, 332, 2),
    (450, 278, 1),
]


def test_regression_hyuptag_no_rotation():
    """협탁 테스트 (회전 불허) — 기존 동작 재현."""
    packer = RegionBasedPacker(
        [(2440, 1220, 10)], kerf=5, allow_rotation=False
    )
    plates, unplaced = packer.pack(HYUPTAG_PIECES)
    placed = sum(len(p['pieces']) for p in plates)
    total = sum(c for _, _, c in HYUPTAG_PIECES)
    assert placed == total, f"{placed}/{total} 배치"
    assert unplaced == [], "모든 조각이 배치되어야 함"


def test_regression_basic_rotation():
    """기본 테스트 케이스 (회전 허용)."""
    packer = RegionBasedPacker(
        [(2440, 1220, 5)], kerf=5, allow_rotation=True
    )
    plates, unplaced = packer.pack(
        [(800, 310, 2), (644, 310, 3), (371, 270, 4), (369, 640, 2)]
    )
    placed = sum(len(p['pieces']) for p in plates)
    assert placed == 11, f"{placed}/11 배치"
    assert unplaced == []


def test_plate_dict_has_dimensions():
    """각 plate에 width/height 포함 확인."""
    packer = RegionBasedPacker(
        [(2440, 1220, 2)], kerf=5, allow_rotation=True
    )
    plates, _ = packer.pack([(800, 310, 2)])
    assert plates, "최소 1장"
    for p in plates:
        assert 'width' in p and 'height' in p
        assert p['width'] == 2440 and p['height'] == 1220


def test_mixed_inventory_uses_both_stocks():
    """혼합 재고: 큰 원판 1장으로 부족 → 작은 원판 보조 필요."""
    packer = RegionBasedPacker(
        [(2440, 1220, 1), (1000, 600, 5)],
        kerf=5,
        allow_rotation=True,
    )
    # 30개 × 400×300 = 3.6M mm² > 큰 원판 2.97M mm²
    # 큰 원판 1장 + 작은 원판 일부가 필요
    plates, unplaced = packer.pack([(400, 300, 30)])

    placed = sum(len(p['pieces']) for p in plates)
    assert placed == 30, f"{placed}/30 배치"
    assert unplaced == []
    sizes = {(p['width'], p['height']) for p in plates}
    assert (2440, 1220) in sizes, "큰 원판이 사용되어야 함"
    assert (1000, 600) in sizes, "작은 원판도 보조로 사용되어야 함"


def test_stock_count_respected():
    """Stock count를 초과해서 사용하지 않음."""
    packer = RegionBasedPacker(
        [(2440, 1220, 1)],
        kerf=5,
        allow_rotation=True,
    )
    plates, unplaced = packer.pack([(2000, 1000, 5)])
    assert len(plates) == 1, f"원판 1장만 사용해야 하는데 {len(plates)}장"
    # 1장에 일부만 들어가고 나머지는 미배치 — 명시 리포트 확인
    placed = sum(len(p['pieces']) for p in plates)
    assert placed + len(unplaced) == 5


def test_bias_prefers_one_large_plate_over_many_small():
    """한 장의 큰 원판에 모두 들어가는 케이스 — 작은 원판 여러 장을 쓰면 안 됨.

    순수 utilization 기반이면 작은 원판에 빽빽이 채우는 쪽이 이기기 쉬움.
    pieces_placed 우선 편향이 제대로 작동하면 큰 원판 1장으로 끝내야 함.
    """
    packer = RegionBasedPacker(
        [(2440, 1220, 1), (600, 400, 5)],
        kerf=5,
        allow_rotation=True,
    )
    plates, unplaced = packer.pack([(500, 400, 4), (300, 200, 3)])

    placed = sum(len(p['pieces']) for p in plates)
    assert placed == 7, f"{placed}/7 배치"
    assert unplaced == []
    assert len(plates) == 1, f"큰 원판 1장이면 충분한데 {len(plates)}장 사용"
    assert plates[0]['width'] == 2440, "큰 원판을 선택해야 함"


def test_empty_stocks_raises():
    """stocks 비면 즉시 에러."""
    with pytest.raises(ValueError, match="최소 1개"):
        RegionBasedPacker([], kerf=5, allow_rotation=True)


def test_invalid_stock_raises():
    """음수/0 stock 거부."""
    with pytest.raises(ValueError, match="양수"):
        RegionBasedPacker([(2440, 1220, 0)], kerf=5, allow_rotation=True)
    with pytest.raises(ValueError, match="양수"):
        RegionBasedPacker([(-100, 1220, 1)], kerf=5, allow_rotation=True)


def test_piece_larger_than_all_stocks():
    """모든 stock보다 큰 조각: 배치 실패 + 조기 종료 (무한루프 아님)."""
    packer = RegionBasedPacker(
        [(1000, 500, 3)], kerf=5, allow_rotation=True,
    )
    plates, unplaced = packer.pack([(2000, 1000, 1)])
    placed = sum(len(p['pieces']) for p in plates)
    assert placed == 0
    # 배치 실패 조각은 명시 리포트되어야 함
    assert len(unplaced) == 1
    assert unplaced[0]['width'] == 2000
    assert unplaced[0]['height'] == 1000


def test_stock_exhaustion_reports_unplaced():
    """Stock 고갈 시 남은 조각이 unplaced 리스트로 명시 리포트되어야 함."""
    packer = RegionBasedPacker(
        [(600, 400, 1)],
        kerf=5,
        allow_rotation=True,
    )
    plates, unplaced = packer.pack([(500, 300, 10)])
    placed = sum(len(p['pieces']) for p in plates)
    assert placed < 10, "1장에 다 못 들어감"
    assert len(plates) == 1
    # 불변식: 배치 + 미배치 == 총 입력
    assert placed + len(unplaced) == 10
    assert len(unplaced) > 0, "미배치 조각이 명시 리포트되어야 함"
    # 모든 미배치 조각은 원래 크기(500×300) 유지
    for p in unplaced:
        assert (p['width'], p['height']) == (500, 300)
