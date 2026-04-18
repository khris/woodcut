"""멀티 stock 통합 테스트 — 회귀/신규/편향/엣지."""
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
    plates = packer.pack(HYUPTAG_PIECES)
    placed = sum(len(p['pieces']) for p in plates)
    total = sum(c for _, _, c in HYUPTAG_PIECES)
    assert placed == total, f"{placed}/{total} 배치"


def test_regression_basic_rotation():
    """기본 테스트 케이스 (회전 허용)."""
    packer = RegionBasedPacker(
        [(2440, 1220, 5)], kerf=5, allow_rotation=True
    )
    plates = packer.pack(
        [(800, 310, 2), (644, 310, 3), (371, 270, 4), (369, 640, 2)]
    )
    placed = sum(len(p['pieces']) for p in plates)
    assert placed == 11, f"{placed}/11 배치"


def test_plate_dict_has_dimensions():
    """각 plate에 width/height 포함 확인."""
    packer = RegionBasedPacker(
        [(2440, 1220, 2)], kerf=5, allow_rotation=True
    )
    plates = packer.pack([(800, 310, 2)])
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
    plates = packer.pack([(400, 300, 30)])

    placed = sum(len(p['pieces']) for p in plates)
    assert placed == 30, f"{placed}/30 배치"
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
    plates = packer.pack([(2000, 1000, 5)])
    assert len(plates) == 1, f"원판 1장만 사용해야 하는데 {len(plates)}장"
