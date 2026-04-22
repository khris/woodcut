"""Guillotine tree primitives (.solution/011).

핵심 아이디어
-------------
- `GNode` 1개 = plate 좌표계의 직사각형 영역 1개.
- internal 노드(= `cut_dir`가 있음) 1개 = Guillotine 컷 1개. 자기 영역 전체를
  관통하는 직선 절단으로 `first`/`second` 두 자식 영역을 만든다.
- leaf 노드 = 더 이상 쪼개지 않는 영역 (조각 1개 담거나, 스크랩 kerf/여백).

이 자료구조의 **불변식이 지켜지는 한 Guillotine 제약은 공리적으로 참**이다.
- 각 internal 노드의 컷은 자기 노드의 직사각형 전체를 관통함이 보장됨.
- cut emit은 전위 순회만 하면 Guillotine 실행 순서가 자연스럽게 나옴.
- `priority`·`dedup` 같은 우회가 필요 없다. start/end 범위가 노드 영역에서
  자동 유도되기 때문.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

CutDir = Literal['H', 'V']
LeafKind = Literal['piece', 'scrap', 'kerf']


@dataclass
class GNode:
    """Guillotine tree node.

    Attributes
    ----------
    x, y, w, h
        plate 좌표계의 이 노드 직사각형.
    cut_dir, cut_pos
        internal 노드에서 이 노드 영역을 쪼개는 컷의 방향과 위치(절대 좌표).
        - 'H' 컷: `cut_pos`는 y 좌표. `first`는 위쪽(y < cut_pos), `second`는
          아래쪽(y ≥ cut_pos + kerf).
        - 'V' 컷: `cut_pos`는 x 좌표. `first`는 왼쪽, `second`는 오른쪽.
        leaf면 둘 다 None.
    first, second
        internal 노드의 두 자식. leaf면 None.
    piece
        leaf에 배치된 조각 dict (placed_w/h, rotated 포함). 스크랩이면 None.
    kind
        leaf 종류 힌트: 'piece' | 'scrap' | 'kerf'.
    meta
        시각화·디버깅 태그. cut emit시 type 필드로 전달할 수 있음.
    """

    x: int
    y: int
    w: int
    h: int

    cut_dir: Optional[CutDir] = None
    cut_pos: Optional[int] = None
    first: Optional['GNode'] = None
    second: Optional['GNode'] = None

    piece: Optional[dict[str, Any]] = None
    kind: Optional[LeafKind] = None
    meta: dict[str, Any] = field(default_factory=dict)

    # ---- 편의 프로퍼티 ----

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    @property
    def is_leaf(self) -> bool:
        return self.cut_dir is None

    def leaves(self) -> list['GNode']:
        """모든 leaf 노드를 전위 순서로 반환."""
        out: list[GNode] = []
        _collect_leaves(self, out)
        return out


def _collect_leaves(node: GNode, out: list[GNode]) -> None:
    if node.is_leaf:
        out.append(node)
        return
    assert node.first is not None and node.second is not None
    _collect_leaves(node.first, out)
    _collect_leaves(node.second, out)


# ---------------- 분할 ----------------


def split_h(node: GNode, cut_y: int, kerf: int) -> tuple[GNode, GNode]:
    """노드를 y=cut_y에서 수평으로 쪼개 (top, bottom) 자식 반환.

    위쪽 자식은 [y, cut_y), 아래쪽 자식은 [cut_y + kerf, y + h).

    `cut_y`는 노드 내부여야 하고 두 자식 모두 양수 높이를 가져야 한다.
    """
    if node.cut_dir is not None:
        raise ValueError("split_h: node already has a cut")
    if not (node.y < cut_y < node.y + node.h):
        raise ValueError(f"split_h: cut_y={cut_y} outside node y=[{node.y},{node.y + node.h})")
    top_h = cut_y - node.y
    bot_y = cut_y + kerf
    bot_h = node.y + node.h - bot_y
    if top_h <= 0 or bot_h <= 0:
        raise ValueError(
            f"split_h: invalid children heights (top={top_h}, bot={bot_h}) — kerf {kerf} overflow?"
        )
    top = GNode(x=node.x, y=node.y, w=node.w, h=top_h)
    bot = GNode(x=node.x, y=bot_y, w=node.w, h=bot_h)
    node.cut_dir = 'H'
    node.cut_pos = cut_y
    node.first = top
    node.second = bot
    return top, bot


def split_v(node: GNode, cut_x: int, kerf: int) -> tuple[GNode, GNode]:
    """노드를 x=cut_x에서 수직으로 쪼개 (left, right) 자식 반환."""
    if node.cut_dir is not None:
        raise ValueError("split_v: node already has a cut")
    if not (node.x < cut_x < node.x + node.w):
        raise ValueError(f"split_v: cut_x={cut_x} outside node x=[{node.x},{node.x + node.w})")
    left_w = cut_x - node.x
    right_x = cut_x + kerf
    right_w = node.x + node.w - right_x
    if left_w <= 0 or right_w <= 0:
        raise ValueError(
            f"split_v: invalid children widths (left={left_w}, right={right_w}) — kerf {kerf} overflow?"
        )
    left = GNode(x=node.x, y=node.y, w=left_w, h=node.h)
    right = GNode(x=right_x, y=node.y, w=right_w, h=node.h)
    node.cut_dir = 'V'
    node.cut_pos = cut_x
    node.first = left
    node.second = right
    return left, right


# ---------------- cut emit ----------------


def emit_cuts(root: GNode) -> list[dict[str, Any]]:
    """전위 순회로 cut 리스트 생성. order는 순회 순서 그대로.

    각 cut dict는 기존 packer/visualizer가 쓰던 스키마와 호환:
    `direction`, `position`, `start`, `end`, `priority`, `order`, `type`,
    `sub_priority` (모두 채움. priority는 order와 동일한 값으로 뒤호환).
    """
    out: list[dict[str, Any]] = []
    _emit(root, out)
    for idx, c in enumerate(out):
        c['order'] = idx + 1
        c.setdefault('priority', idx + 1)
        c.setdefault('sub_priority', 0)
    return out


def _emit(node: GNode, out: list[dict[str, Any]]) -> None:
    if node.is_leaf:
        return
    assert node.cut_dir is not None and node.cut_pos is not None
    assert node.first is not None and node.second is not None
    if node.cut_dir == 'H':
        start, end = node.x, node.x + node.w
    else:
        start, end = node.y, node.y + node.h
    out.append({
        'direction': node.cut_dir,
        'position': node.cut_pos,
        'start': start,
        'end': end,
        'type': node.meta.get('type', 'split'),
        'region_x': node.x,
        'region_y': node.y,
        'region_w': node.w,
        'region_h': node.h,
    })
    _emit(node.first, out)
    _emit(node.second, out)


# ---------------- 불변식 검증 ----------------


def validate_guillotine(root: GNode, kerf: int, tol: int = 1) -> list[str]:
    """트리 불변식을 확인하고 위반 목록 반환. 비어 있으면 OK.

    체크 항목
    ---------
    1. 모든 노드는 leaf 또는 (cut_dir, cut_pos, first, second) 모두 있음.
    2. internal 노드의 컷이 자기 영역 내부 (경계 제외).
    3. first/second가 cut + kerf 기준으로 정확히 양분.
    4. 자식 영역이 부모 영역 안에 포함.
    5. leaf의 piece 경계가 leaf 직사각형 안 (±tol).
    6. 조각들 사이 물리적 겹침 없음 (leaf 단위로 자동 보장되므로 스캔만).
    """
    errors: list[str] = []
    _validate_node(root, kerf, tol, errors, path='root')
    return errors


def _validate_node(
    node: GNode,
    kerf: int,
    tol: int,
    errors: list[str],
    path: str,
) -> None:
    if node.w <= 0 or node.h <= 0:
        errors.append(f"{path}: non-positive size ({node.w}x{node.h})")
        return

    if node.is_leaf:
        if node.piece is not None:
            px = node.piece.get('x')
            py = node.piece.get('y')
            pw = node.piece.get('placed_w', node.piece.get('width'))
            ph = node.piece.get('placed_h', node.piece.get('height'))
            if px is None or py is None or pw is None or ph is None:
                errors.append(f"{path}: piece missing x/y/placed_w/h: {node.piece}")
                return
            if (
                px < node.x - tol or py < node.y - tol or
                px + pw > node.x2 + tol or py + ph > node.y2 + tol
            ):
                errors.append(
                    f"{path}: piece rect ({px},{py},{pw}x{ph}) escapes node "
                    f"({node.x},{node.y},{node.w}x{node.h})"
                )
        return

    # internal
    if node.cut_dir is None or node.cut_pos is None:
        errors.append(f"{path}: internal node missing cut_dir/pos")
        return
    if node.first is None or node.second is None:
        errors.append(f"{path}: internal node missing children")
        return

    cd, cp = node.cut_dir, node.cut_pos
    if cd == 'H':
        if not (node.y < cp < node.y2):
            errors.append(f"{path}: H cut_pos={cp} outside [{node.y},{node.y2})")
        # first = top, second = bottom
        exp_top = (node.x, node.y, node.w, cp - node.y)
        exp_bot = (node.x, cp + kerf, node.w, node.y2 - (cp + kerf))
        _expect_rect(node.first, exp_top, errors, f"{path}.first(top)")
        _expect_rect(node.second, exp_bot, errors, f"{path}.second(bot)")
    else:
        if not (node.x < cp < node.x2):
            errors.append(f"{path}: V cut_pos={cp} outside [{node.x},{node.x2})")
        exp_left = (node.x, node.y, cp - node.x, node.h)
        exp_right = (cp + kerf, node.y, node.x2 - (cp + kerf), node.h)
        _expect_rect(node.first, exp_left, errors, f"{path}.first(left)")
        _expect_rect(node.second, exp_right, errors, f"{path}.second(right)")

    _validate_node(node.first, kerf, tol, errors, f"{path}.first")
    _validate_node(node.second, kerf, tol, errors, f"{path}.second")


def _expect_rect(
    node: GNode,
    expected: tuple[int, int, int, int],
    errors: list[str],
    path: str,
) -> None:
    ex, ey, ew, eh = expected
    if (node.x, node.y, node.w, node.h) != (ex, ey, ew, eh):
        errors.append(
            f"{path}: rect ({node.x},{node.y},{node.w}x{node.h}) "
            f"!= expected ({ex},{ey},{ew}x{eh})"
        )
