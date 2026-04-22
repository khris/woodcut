"""GNode 단위 smoke — .solution/011 11-2.

확인:
- emit_cuts가 전위 순회 순서를 그대로 order로 매긴다.
- cut의 start/end가 해당 노드의 x/w (또는 y/h) 그대로다.
- validate_guillotine이 양분 불변식을 잡아낸다.
- 트리가 emit한 cut list는 test_comprehensive_validation의 엄격 validator도 통과.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))

from woodcut.strategies.gnode import (
    GNode,
    emit_cuts,
    split_h,
    split_v,
    validate_guillotine,
)
from test_comprehensive_validation import validate_guillotine_order


KERF = 5


def t_leaf_only():
    root = GNode(x=0, y=0, w=1000, h=500)
    cuts = emit_cuts(root)
    assert cuts == [], f"leaf-only tree should emit no cuts, got {cuts}"
    errs = validate_guillotine(root, kerf=KERF)
    assert errs == [], f"leaf-only tree should validate clean, got {errs}"
    print("  [OK] leaf_only")


def t_single_h_split():
    root = GNode(x=0, y=0, w=1000, h=500)
    top, bot = split_h(root, cut_y=200, kerf=KERF)
    assert (top.x, top.y, top.w, top.h) == (0, 0, 1000, 200)
    assert (bot.x, bot.y, bot.w, bot.h) == (0, 205, 1000, 295)

    cuts = emit_cuts(root)
    assert len(cuts) == 1
    c = cuts[0]
    assert c['direction'] == 'H' and c['position'] == 200
    assert c['start'] == 0 and c['end'] == 1000
    assert c['order'] == 1

    errs = validate_guillotine(root, kerf=KERF)
    assert errs == [], f"expected clean, got {errs}"

    # 기존 엄격 validator도 통과해야 함
    strict_errs: list[str] = []
    validate_guillotine_order(cuts, pw=1000, ph=500, errors=strict_errs, ctx='t_single_h')
    assert strict_errs == [], f"strict validator failed: {strict_errs}"
    print("  [OK] single_h_split")


def t_h_then_v_preorder():
    """H → V 순으로 쪼개면 전위 순회가 H, (top) V, (bot) 순서대로 번호 매김."""
    root = GNode(x=0, y=0, w=1000, h=500)
    top, bot = split_h(root, cut_y=200, kerf=KERF)
    # top 안에서 다시 V 쪼개기
    left, right = split_v(top, cut_x=400, kerf=KERF)

    cuts = emit_cuts(root)
    assert len(cuts) == 2
    assert cuts[0]['direction'] == 'H' and cuts[0]['order'] == 1
    # 전위: 루트 → first(top) → top의 컷 V → top.first(left) → top.second(right) → 루트.second(bot)
    assert cuts[1]['direction'] == 'V' and cuts[1]['order'] == 2
    # V 컷의 start/end가 top 노드의 y/h 범위와 일치
    assert cuts[1]['start'] == 0 and cuts[1]['end'] == 200
    assert cuts[1]['position'] == 400

    errs = validate_guillotine(root, kerf=KERF)
    assert errs == [], f"expected clean, got {errs}"

    strict_errs: list[str] = []
    validate_guillotine_order(cuts, pw=1000, ph=500, errors=strict_errs, ctx='t_h_then_v')
    assert strict_errs == [], f"strict validator failed: {strict_errs}"

    # leaf 개수 확인: left, right, bot → 3개
    leaves = root.leaves()
    assert len(leaves) == 3
    # 전위 순서로 leaf도 수집되는지
    assert leaves[0] is left
    assert leaves[1] is right
    assert leaves[2] is bot
    print("  [OK] h_then_v_preorder")


def t_invariant_violation_detected():
    """자식 rect를 강제 손상시켜 validator가 잡는지."""
    root = GNode(x=0, y=0, w=1000, h=500)
    top, bot = split_h(root, cut_y=200, kerf=KERF)
    # 불법: top의 w를 줄여 부모와 양분 관계 깨뜨림
    top.w = 900
    errs = validate_guillotine(root, kerf=KERF)
    assert errs, "expected invariant violation to be detected"
    assert any("first(top)" in e for e in errs)
    print("  [OK] invariant_violation_detected")


def t_piece_leaf_contained():
    """leaf에 piece가 안 들어가면 validator가 잡음."""
    root = GNode(x=0, y=0, w=1000, h=500)
    left, right = split_v(root, cut_x=400, kerf=KERF)
    left.piece = {
        'width': 300, 'height': 400,
        'x': 0, 'y': 0, 'rotated': False,
        'placed_w': 300, 'placed_h': 400,
    }
    left.kind = 'piece'
    errs = validate_guillotine(root, kerf=KERF)
    assert errs == [], f"expected clean, got {errs}"

    # 조각이 leaf 밖으로 튀어나가면?
    left.piece['placed_w'] = 500  # left.w=400인데 500이면 오류
    errs = validate_guillotine(root, kerf=KERF)
    assert errs and any("escapes node" in e for e in errs)
    print("  [OK] piece_leaf_contained")


def t_deep_chain_matches_repro_topology():
    """.solution/010 재현 케이스의 기대 위상 흉내:
       plate → H 분할(scrap) → V 분할(2000 앞뒤) → 오른쪽 안에서 H 764 분할.
       cut 순서가 Guillotine 위반 없이 나와야 함."""
    root = GNode(x=0, y=0, w=2440, h=1220)
    working, scrap = split_h(root, cut_y=1145, kerf=KERF)
    # working(0,0,2440,1145)를 V=2000으로 좌우 분할
    left, right = split_v(working, cut_x=2000, kerf=KERF)
    # right(2005,0,435,1145)를 H=764로 상하 분할
    r_top, r_bot = split_h(right, cut_y=764, kerf=KERF)

    cuts = emit_cuts(root)
    # 전위: 루트 H1145 → working.V2000 → left(leaf) → right.H764 → r_top/r_bot → scrap
    assert [c['direction'] for c in cuts] == ['H', 'V', 'H']
    assert cuts[0]['position'] == 1145 and cuts[0]['order'] == 1
    assert cuts[1]['position'] == 2000 and cuts[1]['order'] == 2
    assert cuts[2]['position'] == 764 and cuts[2]['order'] == 3
    # right 노드의 H 컷 start/end가 (2005, 2440)
    assert cuts[2]['start'] == 2005 and cuts[2]['end'] == 2440

    errs = validate_guillotine(root, kerf=KERF)
    assert errs == [], f"expected clean, got {errs}"

    # 엄격 validator도 통과
    strict_errs: list[str] = []
    validate_guillotine_order(cuts, pw=2440, ph=1220, errors=strict_errs, ctx='repro_mock')
    assert strict_errs == [], f"strict validator failed: {strict_errs}"
    print("  [OK] deep_chain_matches_repro_topology")


def main():
    tests = [
        t_leaf_only,
        t_single_h_split,
        t_h_then_v_preorder,
        t_invariant_violation_detected,
        t_piece_leaf_contained,
        t_deep_chain_matches_repro_topology,
    ]
    print("GNode smoke:")
    for t in tests:
        t()
    print(f"PASS — {len(tests)} tests")


if __name__ == '__main__':
    main()
