"""Stock 선택 로직 단위 테스트

select_best_stock: 후보 중 (pieces_placed, utilization) 사전식 최고를 선택.
Lookahead 시뮬레이션 결과를 입력으로 받음 (실제 packing은 mocking).
"""
from woodcut.strategies.region_based import select_best_stock


def test_selects_stock_with_most_pieces_placed():
    """조각 수 많은 쪽이 utilization 낮아도 우선."""
    # 후보: (stock_index, pieces_placed, utilization)
    candidates = [
        (0, 3, 0.9),   # 작은 원판, 빽빽하지만 3개만
        (1, 7, 0.5),   # 큰 원판, 엉성하지만 7개 흡수
    ]
    assert select_best_stock(candidates) == 1


def test_utilization_is_tiebreaker():
    """조각 수 같으면 utilization 높은 쪽."""
    candidates = [
        (0, 5, 0.7),
        (1, 5, 0.9),
        (2, 5, 0.6),
    ]
    assert select_best_stock(candidates) == 1


def test_input_order_is_final_tiebreaker():
    """조각 수도 utilization도 같으면 입력 순서(첫번째) 선택."""
    candidates = [
        (0, 5, 0.8),
        (1, 5, 0.8),
        (2, 5, 0.8),
    ]
    assert select_best_stock(candidates) == 0


def test_empty_candidates_returns_none():
    """후보 없으면 None."""
    assert select_best_stock([]) is None


def test_single_candidate():
    """후보 하나면 그것."""
    assert select_best_stock([(0, 5, 0.7)]) == 0
