"""조각 물리적 겹침 검증 — 회귀 방지선.

기존 "조각 크기 검증"은 개별 조각의 W/H만 확인하므로 두 조각이 같은 좌표에
배치되는 버그를 감지하지 못했다. 이 모듈은 모든 조각 쌍의 bounding box
교차 여부를 직접 확인한다.
"""
from __future__ import annotations

import pytest

from woodcut.strategies.region_based import RegionBasedPacker


def _piece_box(p: dict) -> tuple[int, int, int, int]:
    """조각의 bounding box (x0, y0, x1, y1) — kerf 불포함."""
    x = p['x']
    y = p['y']
    w = p.get('placed_w', p['width'])
    h = p.get('placed_h', p['height'])
    return x, y, x + w, y + h


def _rects_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    """두 직사각형의 넓이 있는 교집합 존재 여부."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


def assert_no_piece_overlap(plate: dict) -> None:
    """Plate 내 모든 조각 쌍에 대해 bounding box가 교차하지 않음을 단언."""
    pieces = plate['pieces']
    for i in range(len(pieces)):
        for j in range(i + 1, len(pieces)):
            a_box = _piece_box(pieces[i])
            b_box = _piece_box(pieces[j])
            if _rects_overlap(a_box, b_box):
                raise AssertionError(
                    f"조각 겹침 발견: [{i}] {a_box} vs [{j}] {b_box}\n"
                    f"  [{i}] {pieces[i]}\n"
                    f"  [{j}] {pieces[j]}"
                )


def assert_pieces_within_plate(plate: dict) -> None:
    """조각이 원판 경계를 벗어나지 않음을 단언."""
    pw, ph = plate['width'], plate['height']
    for i, p in enumerate(plate['pieces']):
        x0, y0, x1, y1 = _piece_box(p)
        if x0 < 0 or y0 < 0 or x1 > pw or y1 > ph:
            raise AssertionError(
                f"조각이 원판 밖: [{i}] box=({x0},{y0},{x1},{y1}) plate={pw}×{ph}"
            )


def _run(stocks, pieces, *, kerf=5, allow_rotation=False):
    packer = RegionBasedPacker(stocks, kerf=kerf, allow_rotation=allow_rotation)
    return packer.pack(pieces)


# ─────────────────────────────────────────────────────────────
# 회귀 케이스 1: 현재 P0 버그 — 스택된 조각 위에 trim이 겹쳐짐
# ─────────────────────────────────────────────────────────────
def test_no_overlap_stacked_trim_bug():
    """2000×280 stacked 그룹 위에 764×100이 겹쳐 배치되는 P0 버그.

    현재 구현에서는 조각 [2] 와 [3] 이 모두 (0, 285) 에 놓여 겹친다.
    Phase B 재작성 후 pass 해야 한다.
    """
    plates, unplaced = _run(
        [(2440, 1220, 2)],
        [(2000, 280, 2), (760, 260, 7), (764, 100, 1)],
        allow_rotation=False,
    )
    for plate in plates:
        assert_pieces_within_plate(plate)
        assert_no_piece_overlap(plate)

    placed = sum(len(p['pieces']) for p in plates)
    assert placed + len(unplaced) == 10


# ─────────────────────────────────────────────────────────────
# 회귀 케이스 2: 협탁 (메모리 preset) — 기존 통과, 유지 확인
# ─────────────────────────────────────────────────────────────
HYUPTAG_PIECES = [
    (560, 350, 2),
    (446, 50, 2),
    (369, 50, 2),
    (550, 450, 1),
    (450, 100, 1),
    (450, 332, 2),
    (450, 278, 1),
]


def test_no_overlap_hyuptag_no_rotation():
    """협탁 preset (회전 불허) — 겹침 없어야 함."""
    plates, unplaced = _run(
        [(2440, 1220, 10)],
        HYUPTAG_PIECES,
        allow_rotation=False,
    )
    for plate in plates:
        assert_pieces_within_plate(plate)
        assert_no_piece_overlap(plate)
    assert unplaced == []


# ─────────────────────────────────────────────────────────────
# 회귀 케이스 3: 기본 회전 허용 — 기존 통과, 유지 확인
# ─────────────────────────────────────────────────────────────
def test_no_overlap_basic_rotation():
    """기본 케이스 (회전 허용) — 겹침 없어야 함."""
    plates, unplaced = _run(
        [(2440, 1220, 5)],
        [(800, 310, 2), (644, 310, 3), (371, 270, 4), (369, 640, 2)],
        allow_rotation=True,
    )
    for plate in plates:
        assert_pieces_within_plate(plate)
        assert_no_piece_overlap(plate)
    assert unplaced == []


# ─────────────────────────────────────────────────────────────
# 헬퍼 자체 단위 테스트 (자가 검증)
# ─────────────────────────────────────────────────────────────
def test_helper_detects_overlap():
    """헬퍼가 명백한 겹침을 잡는지 확인."""
    plate = {
        'width': 100, 'height': 100, 'pieces': [
            {'x': 0, 'y': 0, 'width': 50, 'height': 50, 'placed_w': 50, 'placed_h': 50},
            {'x': 20, 'y': 20, 'width': 50, 'height': 50, 'placed_w': 50, 'placed_h': 50},
        ],
    }
    with pytest.raises(AssertionError, match="조각 겹침"):
        assert_no_piece_overlap(plate)


def test_helper_accepts_touching_edges():
    """경계가 닿기만 하는 조각은 겹침이 아님."""
    plate = {
        'width': 100, 'height': 100, 'pieces': [
            {'x': 0, 'y': 0, 'width': 50, 'height': 50, 'placed_w': 50, 'placed_h': 50},
            {'x': 50, 'y': 0, 'width': 50, 'height': 50, 'placed_w': 50, 'placed_h': 50},
        ],
    }
    assert_no_piece_overlap(plate)  # no raise


def test_helper_detects_out_of_bounds():
    """조각이 원판 경계 밖이면 잡아야 함."""
    plate = {
        'width': 100, 'height': 100, 'pieces': [
            {'x': 80, 'y': 0, 'width': 50, 'height': 50, 'placed_w': 50, 'placed_h': 50},
        ],
    }
    with pytest.raises(AssertionError, match="원판 밖"):
        assert_pieces_within_plate(plate)
