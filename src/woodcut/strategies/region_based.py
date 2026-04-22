"""영역 기반 패킹 전략 - 높이/너비 혼합 그룹화

사용자 수동 배치 패턴을 구현한 알고리즘:
- 각 조각의 회전/비회전 옵션 모두 고려
- 높이 기반 + 너비 기반 클러스터링
- 수평 절단 + 수직 절단 영역 혼합
- 작업 편의성: 같은 높이/너비 조각들이 그룹화
"""

from __future__ import annotations
from ..packing import PackingStrategy, FreeSpace
from .gnode import GNode, emit_cuts, split_h, split_v, validate_guillotine
from .rect import Rect, intersects


def select_best_stock(
    candidates: list[tuple[int, int, float]]
) -> int | None:
    """사전식 비교로 최적 stock index 선택.

    Args:
        candidates: [(stock_index, pieces_placed, utilization), ...]

    Returns:
        최고 후보의 stock_index, 후보 없으면 None.

    규칙:
        1차: pieces_placed 내림차순
        2차: utilization 내림차순
        3차: 입력 순서(작은 index) — max가 후행 동점을 덮어쓰지 않게 처리
    """
    if not candidates:
        return None

    # max()는 동점 시 앞의 것을 유지 — (pieces, util) 역순 비교로 OK
    best = max(candidates, key=lambda c: (c[1], c[2]))
    return best[0]


class RegionBasedPacker(PackingStrategy):
    """전략 6: 높이/너비 혼합 그룹화 패킹

    핵심 아이디어:
    - 각 조각의 회전/비회전 옵션 모두 고려
    - 높이 기반 + 너비 기반 클러스터링
    - 수평 절단 + 수직 절단 영역 혼합
    - 작업 편의성: 같은 높이/너비 조각들이 그룹화
    """

    def pack(
        self, pieces: list[tuple[int, int, int]]
    ) -> tuple[list[dict], list[dict]]:
        """멀티 stock 패킹.

        매 iteration마다:
          1. 각 남은 stock 종류에 대해 1장 시뮬레이션
          2. (pieces_placed, utilization) 사전식 최고 stock 선택
          3. 해당 stock count 차감, 배치된 조각 제거

        Returns:
            (plates, unplaced):
                plates: 배치된 판 리스트
                unplaced: 재고 부족/크기 초과로 배치 못 한 조각 dict 리스트
        """
        all_pieces = self.expand_pieces(pieces)
        plates = []
        remaining_pieces = all_pieces[:]
        # stock count 가변 복사 (원본 self.stocks는 유지)
        stock_counts = [s[2] for s in self.stocks]

        plate_num = 1
        while remaining_pieces and any(c > 0 for c in stock_counts):
            print(f"\n=== 원판 {plate_num}: stock 선택 시뮬레이션 ===")

            # 후보별 시뮬레이션
            candidates = []  # (stock_index, pieces_placed, utilization, plate_dict)
            for i, (w, h, _count) in enumerate(self.stocks):
                if stock_counts[i] == 0:
                    continue
                self.plate_width = w
                self.plate_height = h
                trial = self._pack_single_plate(remaining_pieces)
                placed = len(trial['pieces'])
                total_placed_area = sum(
                    p.get('placed_w', p['width']) * p.get('placed_h', p['height'])
                    for p in trial['pieces']
                )
                util = total_placed_area / (w * h) if w * h else 0.0
                candidates.append((i, placed, util, trial))
                print(f"  후보 {i}: {w}×{h} → {placed}개, util={util:.2%}")

            if not candidates:
                print("⚠️  사용 가능 stock 없음")
                break

            scored = [(c[0], c[1], c[2]) for c in candidates]
            best_idx = select_best_stock(scored)
            best_candidate = next(c for c in candidates if c[0] == best_idx)
            _, best_placed, best_util, best_plate = best_candidate
            best_w, best_h, _ = self.stocks[best_idx]

            if best_placed == 0:
                print("⚠️  어느 stock에도 배치 실패 — 종료")
                break

            # 선택된 stock의 dimension으로 self 상태 복원
            # (후보 시뮬레이션 중 마지막 후보 dim으로 오염된 상태를 정리)
            self.plate_width = best_w
            self.plate_height = best_h

            print(
                f"✓ 선택: stock[{best_idx}] {best_w}×{best_h} "
                f"({best_placed}개, {best_util:.2%})"
            )

            plates.append(best_plate)
            stock_counts[best_idx] -= 1

            # 배치된 조각을 remaining에서 제거
            placed_sizes = {}
            for p in best_plate['pieces']:
                size_key = (p['width'], p['height'])
                placed_sizes[size_key] = placed_sizes.get(size_key, 0) + 1

            new_remaining = []
            for piece in remaining_pieces:
                size_key = (piece['width'], piece['height'])
                if size_key in placed_sizes and placed_sizes[size_key] > 0:
                    placed_sizes[size_key] -= 1
                else:
                    new_remaining.append(piece)
            remaining_pieces = new_remaining

            plate_num += 1

        return plates, remaining_pieces

    def _pack_single_plate(self, remaining_pieces: list[dict]) -> dict:
        """현재 self.plate_width/height 기준으로 원판 1장 패킹.

        호출 측에서 self.plate_width/height를 사전에 세팅해야 함.
        remaining_pieces는 수정하지 않음 — 반환된 plate['pieces']로 호출자가 차감.

        Returns:
            plate dict: {'width', 'height', 'pieces', 'cuts', 'free_spaces'}
        """
        # 1. 레벨 1: 정확히 같은 크기끼리 그룹화
        groups = self._group_by_exact_size(remaining_pieces)

        # 2. 각 그룹의 회전 옵션 생성
        group_options = self._generate_group_options(groups)

        # 3. 회전 옵션 평면화
        all_variants = self._flatten_group_options(group_options)

        # 4. 앵커 기반 백트래킹으로 최적 조합 찾기
        regions = self._allocate_anchor_backtrack(all_variants)

        # occupancy 필드 초기화 (Phase A 결과물을 공간 모델로 명시화)
        # Phase B(trim 최적화)가 이 필드를 참조해 stacked 조각 위를 침범하지 않도록 한다.
        if regions:
            self._init_region_occupancy(regions)

        # 영역 간 trim 최적화
        if regions:
            self._optimize_trim_placement(regions)

        # 폴백: Phase A가 regions 생성에 실패하면 shelf packer로 안전 배치.
        # placed_w/h를 명시 설정해 trimming cut 경로를 타지 않도록 한다 (.solution/007)
        if not regions:
            return self._pack_fallback_shelf(remaining_pieces)

        return self._build_plate_from_regions(regions)

    def _build_plate_from_regions(self, regions: list[dict]) -> dict:
        """regions → plate dict 변환.

        자식 클래스와 공유되는 "영역 배치 → 조각/절단선 조립" 로직.
        regions는 비어 있지 않다고 가정 (호출 측 책임).

        .solution/011 B0: plate-level Guillotine tree skeleton을 먼저 빌드한다.
        region 간 경계(`region_boundary`, `scrap_boundary`)는 이 skeleton의
        internal 노드 cut으로 자동 emit되어 dict 경로에서는 만들지 않는다.
        region 내부 cut은 현재로선 dict 경로(`_pack_multi_group_region`)가
        담당하며, 후속 분기(B1~B4)에서 region_node 서브트리 안으로 흡수된다.

        Returns:
            plate dict: {'width', 'height', 'pieces', 'cuts', 'free_spaces'}
        """
        plate = {
            'width': self.plate_width,
            'height': self.plate_height,
            'pieces': [],
            'cuts': [],
            'free_spaces': [],
        }

        # --- plate skeleton tree 빌드 ---
        plate_root = GNode(x=0, y=0, w=self.plate_width, h=self.plate_height)
        cursor: GNode | None = plate_root
        region_nodes: list[GNode | None] = [None] * len(regions)
        for i in range(len(regions) - 1):
            if cursor is None:
                break
            region = regions[i]
            cut_y = region['y'] + region['max_height']
            if not (cursor.y < cut_y < cursor.y2):
                # region이 cursor 범위 밖이면 남은 region_nodes는 미설정 — 이 경로는
                # 이론적으로 발생 안 하지만 안전망.
                region_nodes[i] = cursor
                cursor = None
                break
            boundary = cursor
            region_node, cursor = split_h(boundary, cut_y=cut_y, kerf=self.kerf)
            boundary.meta['type'] = (
                'scrap_boundary' if regions[i + 1]['type'] == 'scrap' else 'region_boundary'
            )
            region_nodes[i] = region_node
        if cursor is not None:
            region_nodes[-1] = cursor

        for i, rn in enumerate(region_nodes):
            if rn is None:
                continue
            if regions[i]['type'] == 'scrap':
                rn.kind = 'scrap'
            rn.meta['region_id'] = f'R{i+1}'

        # --- region별 배치 + 트리 흡수 ---
        for i, region in enumerate(regions):
            region['id'] = f'R{i+1}'

        for i, region in enumerate(regions):
            placed = self._pack_multi_group_region(region)
            if placed:
                plate['pieces'].extend(placed)

            # region 내부를 재귀 guillotine partitioning으로 트리에 흡수.
            # placed 좌표만 보고 V/H 후보를 찾아 서브트리를 만든다.
            # 빈 region(scrap 또는 placed 없음)은 건너뛴다 — leaf 그대로.
            region_node = region_nodes[i] if i < len(region_nodes) else None
            if region_node is not None and placed:
                if not self._build_region_subtree(region_node, placed, region):
                    raise AssertionError(
                        f"region {region['id']}: "
                        f"_build_region_subtree failed — complex layout not absorbed by tree"
                    )

        # tree가 전위 순회 순서로 cut을 emit하므로 priority 기반 sort는 불필요.
        # 모든 cut은 GNode 트리에서 직접 유도 — start/end/order가 노드 직사각형 자동.
        cuts = emit_cuts(plate_root)

        # 불변식 assertion (.solution/011 11-10): tree 구조 자체 체크.
        if __debug__:
            errs = validate_guillotine(plate_root, kerf=self.kerf)
            if errs:
                raise AssertionError(
                    f"Guillotine tree invariant violated: {errs[:3]}"
                )

        for idx, cut in enumerate(cuts):
            cut['order'] = idx + 1
            if 'region_x' not in cut:
                cut['region_x'] = 0
                cut['region_y'] = 0
                cut['region_w'] = self.plate_width
                cut['region_h'] = self.plate_height
        plate['cuts'] = cuts
        plate['_tree_root'] = plate_root
        return plate

    def _pack_fallback_shelf(self, pieces: list[dict]) -> dict:
        """Phase A가 regions를 못 만들 때 쓰는 안전망 (NFDH shelf 배치).

        기존 fallback은 `_find_best_placement_simple` + `generate_guillotine_cuts`
        조합이었지만, 후자가 조각을 영역 경계로 trim해 `placed_w/h`를 오염시키는
        버그가 있었다 (.solution/007). 여기서는 각 조각을 원본 크기 그대로 두고
        `placed_w/h`를 명시 설정해 trim 경로를 차단한다.
        """
        plate = {
            'width': self.plate_width,
            'height': self.plate_height,
            'pieces': [],
            'cuts': [],
            'free_spaces': [],
        }

        # 큰 조각 먼저 (Next-Fit Decreasing Height)
        sorted_pieces = sorted(
            pieces,
            key=lambda p: (-max(p['width'], p['height']), -p['area'])
        )

        shelves: list[dict] = []  # {'y', 'h', 'x_cursor', 'pieces'}
        y_next = 0

        for piece in sorted_pieces:
            w0, h0 = piece['width'], piece['height']
            placed = False

            # shelf h를 최대한 채우는 배향 우선 (ph 내림차순)
            oriented = sorted(
                self._fallback_orientations(w0, h0),
                key=lambda t: -t[1]
            )

            # 1) 기존 shelf에 끼워넣기
            for shelf in shelves:
                for pw, ph, rot in oriented:
                    if ph > shelf['h']:
                        continue
                    if shelf['x_cursor'] + pw > self.plate_width:
                        continue
                    shelf['pieces'].append({
                        **piece,
                        'x': shelf['x_cursor'],
                        'y': shelf['y'],
                        'rotated': rot,
                        'placed_w': pw,
                        'placed_h': ph,
                    })
                    shelf['x_cursor'] += pw + self.kerf
                    placed = True
                    break
                if placed:
                    break
            if placed:
                continue

            # 2) 새 shelf — tall 배향 우선(shelf h 최대화로 후속 포용력↑)
            tall_candidates = oriented

            for pw, ph, rot in tall_candidates:
                if pw > self.plate_width:
                    continue
                if y_next + ph > self.plate_height:
                    continue
                placed_piece = {
                    **piece,
                    'x': 0,
                    'y': y_next,
                    'rotated': rot,
                    'placed_w': pw,
                    'placed_h': ph,
                }
                shelves.append({
                    'y': y_next,
                    'h': ph,
                    'x_cursor': pw + self.kerf,
                    'pieces': [placed_piece],
                })
                y_next += ph + self.kerf
                placed = True
                break
            # placed == False 이면 drop — 상위 loop의 `remaining` 차감이 남겨둔다

        for shelf in shelves:
            plate['pieces'].extend(shelf['pieces'])

        self._emit_fallback_cuts(plate, shelves)
        return plate

    def _fallback_orientations(self, w: int, h: int):
        """폴백 shelf에서 쓸 (pw, ph, rotated) 배향 후보. 비회전 우선."""
        yield (w, h, False)
        if self.allow_rotation and w != h:
            yield (h, w, True)

    def _emit_fallback_cuts(self, plate: dict, shelves: list[dict]) -> None:
        """shelf 기반 Guillotine 절단선 생성 (tree 방식, .solution/011).

        구조:
        - 루트 = plate 전체.
        - shelf 경계(y = shelf_top)마다 H 컷 — 루트를 "shelf + 나머지"로 분할.
        - 각 shelf 내부에서 조각의 우측 edge마다 V 컷 — 조각을 leaf로 떼어냄.
        - 마지막 조각 이후 남은 우측 공간은 scrap leaf, plate top 위 공간도 scrap.

        tree 전위 순회(`emit_cuts`)가 order·start·end를 자동 계산하므로
        별도의 priority 조율이나 dedup이 필요 없다.
        """
        pw = self.plate_width
        ph = self.plate_height

        root = GNode(x=0, y=0, w=pw, h=ph)
        cursor: GNode | None = root  # 다음 shelf가 들어갈 아래쪽 노드

        for shelf in shelves:
            if cursor is None:
                break

            shelf_top = shelf['y'] + shelf['h']
            if shelf_top < cursor.y2:
                # cursor를 (shelf, 나머지 아래쪽)으로 분할. boundary_node는 split을
                # 수행한 객체 자체 — split 후에도 같은 객체라 meta 태그 가능.
                boundary_node = cursor
                shelf_node, cursor = split_h(boundary_node, cut_y=shelf_top, kerf=self.kerf)
                boundary_node.meta['type'] = 'shelf_boundary'
            else:
                # shelf가 cursor 끝에 딱 맞음 — 상단 분할 불필요.
                shelf_node = cursor
                cursor = None

            # shelf 내부 V 컷 연쇄로 조각 분할.
            inner: GNode | None = shelf_node
            shelf_pieces = sorted(shelf['pieces'], key=lambda p: p['x'])
            for i, piece in enumerate(shelf_pieces):
                if inner is None:
                    break
                right_edge = piece['x'] + piece['placed_w']
                # 조각 오른쪽에 kerf 너비도 안 남으면 split_v 불가 — inner 전체를
                # 이 조각으로 마감. (±1mm 경계/톱밥 두께 이하 여분은 무시)
                if right_edge + self.kerf >= inner.x2:
                    inner.piece = piece
                    inner.kind = 'piece'
                    inner = None
                    break
                column_node = inner
                piece_leaf, rest = split_v(column_node, cut_x=right_edge, kerf=self.kerf)
                column_node.meta['type'] = 'shelf_column'
                piece_leaf.piece = piece
                piece_leaf.kind = 'piece'
                inner = rest
            if inner is not None:
                inner.kind = 'scrap'

        # 남은 cursor(plate 상단 scrap)도 leaf로 마감.
        if cursor is not None:
            cursor.kind = 'scrap'

        plate['cuts'] = emit_cuts(root)
        plate['_tree_root'] = root  # 디버그용 — 시각화는 'cuts'만 본다


    def _group_by_exact_size(self, pieces):
        """레벨 1: 정확히 같은 크기의 조각들끼리 그룹화

        Args:
            pieces: 모든 조각 리스트

        Returns:
            List of groups:
            {
                'size': (width, height),  # 그룹의 대표 크기
                'pieces': [...],          # 이 그룹에 속한 조각들
                'count': n,               # 조각 개수
                'total_area': 총 면적
            }
        """
        groups_dict = {}  # (width, height) -> pieces list

        for piece in pieces:
            w, h = piece['width'], piece['height']
            size_key = (w, h)

            if size_key not in groups_dict:
                groups_dict[size_key] = []
            groups_dict[size_key].append(piece)

        # 그룹 리스트로 변환
        groups = []
        for size, piece_list in groups_dict.items():
            groups.append({
                'size': size,
                'pieces': piece_list,
                'count': len(piece_list),
                'total_area': size[0] * size[1] * len(piece_list)
            })

        # 면적이 큰 그룹 우선 (공간 활용률)
        groups.sort(key=lambda g: g['total_area'], reverse=True)

        return groups

    def _generate_group_options(self, groups):
        """각 그룹의 회전/비회전 옵션 생성

        Args:
            groups: _group_by_exact_size()의 결과

        Returns:
            List of dicts:
            {
                'original_size': (width, height),
                'count': n,
                'options': [
                    {'rotated': False, 'height': h, 'width': w},
                    {'rotated': True, 'height': w, 'width': h}
                ]
            }
        """
        group_options = []

        for group in groups:
            w, h = group['size']
            count = group['count']

            options = [
                {'rotated': False, 'height': h, 'width': w}
            ]

            if self.allow_rotation:
                options.append({'rotated': True, 'height': w, 'width': h})

            group_options.append({
                'original_size': (w, h),
                'count': count,
                'options': options
            })

        return group_options

    def _flatten_group_options(self, group_options):
        """회전 옵션을 평면화하여 모든 그룹 변형 목록 생성

        Args:
            group_options: _generate_group_options()의 결과

        Returns:
            List of group variants:
            [
                {
                    'original_size': (w, h),
                    'count': n,
                    'rotated': bool,
                    'stacked': bool,    # 세로 배치 여부
                    'height': int,      # 배치 시 실제 높이
                    'width': int,       # 배치 시 실제 너비
                    'total_width': int, # count * width + (count-1) * kerf
                    'area': int
                },
                ...
            ]
        """
        variants = []

        for group_opt in group_options:
            original_size = group_opt['original_size']
            count = group_opt['count']

            for option in group_opt['options']:
                w = option['width']
                h = option['height']

                # 가로 배치 옵션 (기본)
                total_width_h = (w + self.kerf) * count
                variants.append({
                    'original_size': original_size,
                    'count': count,
                    'rotated': option['rotated'],
                    'stacked': False,  # 가로 배치
                    'height': h,
                    'width': w,
                    'total_width': total_width_h,
                    'area': w * h * count
                })

                # 세로 배치 옵션 (가로 배치가 판재 너비 초과 시)
                if total_width_h > self.plate_width and count > 1:
                    total_height_v = (h + self.kerf) * count
                    # 높이 체크
                    if total_height_v <= self.plate_height:
                        variants.append({
                            'original_size': original_size,
                            'count': count,
                            'rotated': option['rotated'],
                            'stacked': True,  # 세로 배치
                            'height': total_height_v,  # 전체 높이
                            'width': w,
                            'total_width': w + self.kerf,  # 한 조각 너비
                            'area': w * h * count
                        })

        return variants

    def _build_region_with_anchor(self, anchor, all_unused, already_used):
        """앵커를 기준으로 영역에 호환 그룹들 추가

        Args:
            anchor: 앵커 그룹 변형 (max_height 결정)
            all_unused: 아직 사용되지 않은 모든 그룹 변형
            already_used: 이미 사용된 그룹 original_size 집합

        Returns:
            (groups_list, used_original_sizes)
            - groups_list: 영역에 들어갈 그룹 정보 리스트
            - used_original_sizes: 사용된 original_size 집합
        """
        max_height = anchor['height']

        # 앵커 먼저 추가
        groups = [{
            'original_size': anchor['original_size'],
            'rotated': anchor['rotated'],
            'count': anchor['count'],
            'stacked': anchor.get('stacked', False)  # 세로 배치 여부
        }]
        used_sizes = {anchor['original_size']}
        current_width = anchor['total_width']

        # 호환 가능한 그룹 찾기
        compatible = []
        for v in all_unused:
            # 이미 사용된 그룹 스킵
            if v['original_size'] in used_sizes or v['original_size'] in already_used:
                continue

            # 같은 원본 크기인데 다른 회전 옵션인 경우도 스킵
            if v['original_size'] == anchor['original_size']:
                continue

            # 높이 제약: v['height'] <= max_height
            if v['height'] > max_height:
                continue

            # 너비 제약: 추가 후 전체 너비 <= plate_width
            needed_width = self.kerf + v['total_width']
            if current_width + needed_width > self.plate_width:
                continue

            compatible.append(v)

        # 호환 그룹들을 높이 유사도순으로 정렬 (앵커와 비슷한 높이 우선)
        # 이유: 비슷한 높이끼리 배치하면 절단 편의성이 좋고, 더 많은 그룹이 들어갈 수 있음
        compatible.sort(key=lambda v: (abs(max_height - v['height']), -v['area']))

        # 그리디하게 추가
        for v in compatible:
            # 다시 한 번 체크 (이미 다른 회전 옵션으로 추가된 경우)
            if v['original_size'] in used_sizes:
                continue

            needed_width = self.kerf + v['total_width']
            if current_width + needed_width <= self.plate_width:
                groups.append({
                    'original_size': v['original_size'],
                    'rotated': v['rotated'],
                    'count': v['count'],
                    'stacked': v.get('stacked', False)  # 세로 배치 여부
                })
                used_sizes.add(v['original_size'])
                current_width += needed_width

        return groups, used_sizes

    def _allocate_anchor_backtrack(self, all_variants):
        """앵커 그룹 기반 백트래킹으로 최적 영역 배치 찾기

        Args:
            all_variants: _flatten_group_options()의 결과

        Returns:
            List of regions (최적 조합) 또는 []
        """
        # 원본 그룹 크기 집합 (중복 방지용)
        all_original_sizes = {v['original_size'] for v in all_variants}
        total_groups = len(all_original_sizes)

        print(f"\n[앵커 백트래킹] 총 {total_groups}개 그룹, {len(all_variants)}개 변형 옵션")

        def backtrack(used_groups, y_offset):
            """재귀적 백트래킹

            Args:
                used_groups: 이미 사용된 그룹의 original_size 집합
                y_offset: 현재 y 위치

            Returns:
                (best_regions, best_count)
            """
            # 종료 조건: 모든 그룹 배치 완료
            if len(used_groups) == total_groups:
                return [], 0

            best_regions = []
            best_count = 0

            # 미사용 그룹 중 앵커 후보 선택
            unused_variants = [
                v for v in all_variants
                if v['original_size'] not in used_groups
            ]

            # 높이 내림차순 정렬 (높은 앵커 우선 = 더 많은 그룹 수용 가능)
            # 같은 original_size의 다른 회전 옵션 중복 제거
            seen_sizes = set()
            anchor_candidates = []
            for v in sorted(unused_variants, key=lambda x: x['height'], reverse=True):
                if v['original_size'] not in seen_sizes:
                    anchor_candidates.append(v)
                    seen_sizes.add(v['original_size'])
                else:
                    # 같은 크기의 다른 회전 옵션도 후보로 추가
                    anchor_candidates.append(v)

            # 각 앵커 후보로 영역 생성 시도
            for anchor in anchor_candidates:
                # 앵커가 판재 높이를 초과하면 스킵
                region_height = anchor['height'] + self.kerf
                if y_offset + region_height > self.plate_height:
                    continue

                # 앵커가 판재 너비를 초과하면 스킵
                if anchor['total_width'] > self.plate_width:
                    continue

                # 이 앵커로 영역 생성 + 호환 그룹 추가
                region_groups, region_used = self._build_region_with_anchor(
                    anchor,
                    unused_variants,
                    used_groups
                )

                if not region_groups:
                    continue

                # 영역 생성
                region = {
                    'type': 'horizontal',
                    'x': 0,
                    'y': y_offset,
                    'width': self.plate_width,
                    'height': region_height,
                    'max_height': anchor['height'],
                    'rows': [{'groups': region_groups, 'height': region_height}]  # ★ rows 구조
                }

                # 재귀 호출
                new_used = used_groups | region_used
                new_y = y_offset + region_height

                sub_regions, sub_count = backtrack(new_used, new_y)

                # 현재 영역에서 배치된 조각 수
                current_count = sum(g['count'] for g in region_groups)
                total_count = current_count + sub_count

                if total_count > best_count:
                    best_count = total_count
                    best_regions = [region] + sub_regions

            return best_regions, best_count

        regions, count = backtrack(set(), 0)

        # 상단 자투리 영역 추가 (kerf보다 크면 무조건)
        if regions:
            last_region = regions[-1]
            last_region_top = last_region['y'] + last_region['height']
            remaining_height = self.plate_height - last_region_top

            if remaining_height > self.kerf:
                scrap_region = {
                    'type': 'scrap',
                    'x': 0,
                    'y': last_region_top,
                    'width': self.plate_width,
                    'height': remaining_height,
                    'max_height': 0,
                    'rows': [{'groups': [], 'height': 0}]  # ★ rows 구조 (빈 행)
                }
                regions.append(scrap_region)
                print(f"[자투리 영역 추가] y={scrap_region['y']}, height={remaining_height}mm")

        print(f"[앵커 백트래킹 완료] {count}개 조각 배치, {len(regions)}개 영역")

        return regions

    def _build_region_subtree(
        self,
        region_node: GNode,
        placed: list[dict],
        region: dict,
    ) -> bool:
        """region 내부 배치를 region_node 서브트리로 재구성 (.solution/011).

        재귀 guillotine partitioning: `placed` 좌표만 보고 V/H split을 찾아
        전체를 Guillotine tree로 분해한다.

        알고리즘
        --------
        1. pieces가 비면 scrap leaf.
        2. piece가 1개면 왼/오/상/하 여백을 V/H scrap split으로 분리.
        3. pieces 여럿이면:
           - V cut 후보: pieces의 x_end 값 중 하나 — 왼쪽/오른쪽 분리 가능하면 split.
           - H cut 후보: pieces의 y_end 값 중 하나.
           - 어느 방향이든 선 kerf 양쪽 간격이 정확히 kerf여야 함 (배치가 이미 보장).
        4. 어떤 split도 불가 → False 반환 (region_node를 leaf로 복원).

        반환값
        ------
        True: region 전체를 tree로 흡수. 호출측은 이 region의 dict cut을 폐기.
        False: 복잡 케이스. region_node를 leaf로 복원하고 dict 경로 유지.
        """
        if region.get('type') == 'scrap' or not placed:
            return False

        # 빌드 시도 — 실패 시 region_node 전체 복원
        if not self._build_recursive(region_node, list(placed)):
            self._reset_node_recursive(region_node)
            return False
        return True

    def _build_recursive(self, node: GNode, pieces: list[dict]) -> bool:
        """node 영역에 pieces를 Guillotine tree로 재귀 분해."""
        kerf = self.kerf

        if not pieces:
            node.kind = 'scrap'
            return True

        if len(pieces) == 1:
            return self._attach_single_piece(node, pieces[0])

        # V split 후보: pieces 의 x_end 값
        v_candidates = sorted({
            p['x'] + p.get('placed_w', p['width']) for p in pieces
        })
        for cut_x in v_candidates:
            if not (node.x < cut_x < node.x + node.w):
                continue
            left = [
                p for p in pieces
                if p['x'] + p.get('placed_w', p['width']) <= cut_x
            ]
            right = [p for p in pieces if p['x'] >= cut_x + kerf]
            if len(left) + len(right) != len(pieces):
                continue
            if not left or not right:
                continue
            # 오른쪽 첫 piece의 x가 cut_x + kerf와 정확히 일치해야 함
            if min(p['x'] for p in right) != cut_x + kerf:
                continue
            left_node, right_node = split_v(node, cut_x=cut_x, kerf=kerf)
            if (self._build_recursive(left_node, left)
                    and self._build_recursive(right_node, right)):
                return True
            return False

        # H split 후보: pieces 의 y_end 값
        h_candidates = sorted({
            p['y'] + p.get('placed_h', p['height']) for p in pieces
        })
        for cut_y in h_candidates:
            if not (node.y < cut_y < node.y + node.h):
                continue
            top = [
                p for p in pieces
                if p['y'] + p.get('placed_h', p['height']) <= cut_y
            ]
            bot = [p for p in pieces if p['y'] >= cut_y + kerf]
            if len(top) + len(bot) != len(pieces):
                continue
            if not top or not bot:
                continue
            if min(p['y'] for p in bot) != cut_y + kerf:
                continue
            top_node, bot_node = split_h(node, cut_y=cut_y, kerf=kerf)
            if (self._build_recursive(top_node, top)
                    and self._build_recursive(bot_node, bot)):
                return True
            return False

        # 어떤 guillotine split으로도 분리 불가 (겹침/NFDH-incompat)
        return False

    def _attach_single_piece(self, node: GNode, piece: dict) -> bool:
        """node 영역에 piece 하나만 있을 때 주위 scrap을 V/H로 분리하고 leaf 부착.

        순서: 우측 scrap V → 상단 scrap H. 왼쪽/하단 scrap은 이미 상위 split으로
        처리됐다고 가정 (즉 piece 는 node 의 왼쪽 위 모서리에 맞닿아 있음).
        """
        kerf = self.kerf
        pw = piece.get('placed_w', piece['width'])
        ph = piece.get('placed_h', piece['height'])

        # piece가 node 왼쪽 위에 맞닿았는지 (±kerf 오차 허용)
        if abs(piece['x'] - node.x) > kerf or abs(piece['y'] - node.y) > kerf:
            return False

        cur = node
        # 우측 scrap 분리
        right_gap = cur.x + cur.w - (piece['x'] + pw)
        if right_gap > kerf:
            col, right_scrap = split_v(cur, cut_x=piece['x'] + pw, kerf=kerf)
            right_scrap.kind = 'scrap'
            right_scrap.meta['type'] = 'right_trim'
            cur = col
        elif right_gap < -kerf:
            return False

        # 상단 scrap 분리
        top_gap = cur.y + cur.h - (piece['y'] + ph)
        if top_gap > kerf:
            piece_node, top_scrap = split_h(cur, cut_y=piece['y'] + ph, kerf=kerf)
            top_scrap.kind = 'scrap'
            top_scrap.meta['type'] = 'column_top_trim'
            cur = piece_node
        elif top_gap < -kerf:
            return False

        cur.piece = piece
        cur.kind = 'piece'
        return True

    def _reset_node_recursive(self, node: GNode) -> None:
        """node와 그 서브트리를 leaf 상태로 복원 (빌드 실패 rollback)."""
        if node.first is not None:
            self._reset_node_recursive(node.first)
        if node.second is not None:
            self._reset_node_recursive(node.second)
        node.cut_dir = None
        node.cut_pos = None
        node.first = None
        node.second = None
        node.piece = None
        # kind/meta는 region_node 원래 세팅(scrap 힌트 등)을 지우지 않도록 보존
        # — 단 이 메서드는 region_node 자체가 아니라 하위 노드에만 쓰이므로 안전

    def _pack_multi_group_region(self, region: dict) -> list[dict] | None:
        """region에 조각들을 배치하고 placed 리스트 반환.

        절단선 생성은 하지 않는다 — `_build_region_subtree`가 `placed` 좌표만
        보고 재귀 guillotine partitioning으로 tree를 빌드한다(.solution/011).

        Args:
            region: `_allocate_anchor_backtrack`이 만든 영역 정보
                (`x`, `y`, `width`, `height`, `max_height`, `rows`, `type`).

        Returns:
            - scrap region: 빈 리스트.
            - 일반 region: 조각 dict 리스트. 각 dict에 `placed_w`/`placed_h`
              (회전 반영된 실제 배치 크기) 세팅됨.
            - 공간 부족(invalid layout): None.
        """
        placed: list[dict] = []
        region_y = region['y']
        max_height = region['max_height']

        print(f"\n[영역 배치] {region['type']}, y={region_y}, max_height={max_height}")

        # scrap region은 배치 없음 — plate skeleton이 경계 H cut을 이미 emit함
        if region['type'] == 'scrap':
            return placed

        # 다중 행 처리
        current_y = region_y
        for row_idx, row in enumerate(region['rows']):
            current_x = region['x']

            for group in row['groups']:
                w, h = group['original_size']
                rotated = group['rotated']
                count = group['count']
                stacked = group.get('stacked', False)

                piece_w = h if rotated else w
                piece_h = w if rotated else h

                mode_str = "세로" if stacked else "가로"
                print(
                    f"  [행 {row_idx+1}] 그룹 {w}×{h} "
                    f"(회전={rotated}, {mode_str}배치): {count}개 → y={current_y}"
                )

                group_start_x = current_x  # trim_rows 기준점

                if stacked:
                    # 세로 배치: 같은 x에 연속 y로 쌓음
                    for i in range(count):
                        if current_x + piece_w > region['x'] + region['width']:
                            print(
                                f"    ⚠️  공간 부족: x={current_x}, piece_w={piece_w}, "
                                f"region_w={region['width']}"
                            )
                            return None
                        piece_y = current_y + i * (piece_h + self.kerf)
                        placed.append({
                            'width': w, 'height': h,
                            'x': current_x, 'y': piece_y,
                            'rotated': rotated,
                            'id': len(placed),
                            'original': (w, h),
                        })
                    current_x += piece_w + self.kerf
                else:
                    # 가로 배치: 같은 y에 연속 x로 나열
                    for _ in range(count):
                        if current_x + piece_w > region['x'] + region['width']:
                            print(
                                f"    ⚠️  공간 부족: x={current_x}, piece_w={piece_w}, "
                                f"region_w={region['width']}"
                            )
                            return None
                        placed.append({
                            'width': w, 'height': h,
                            'x': current_x, 'y': current_y,
                            'rotated': rotated,
                            'id': len(placed),
                            'original': (w, h),
                        })
                        current_x += piece_w + self.kerf

                # trim_rows: 그룹 안쪽 자투리 공간에 끼워 넣은 조각들
                for trim_row in group.get('trim_rows', []):
                    trim_y = current_y + trim_row['y_offset']
                    trim_x = group_start_x + trim_row.get('x_offset', 0)
                    for trim_group in trim_row['groups']:
                        tw, th = trim_group['original_size']
                        trotated = trim_group['rotated']
                        tpiece_w = th if trotated else tw
                        for _ in range(trim_group['count']):
                            if trim_x + tpiece_w > region['x'] + region['width']:
                                break
                            placed.append({
                                'width': tw, 'height': th,
                                'x': trim_x, 'y': trim_y,
                                'rotated': trotated,
                                'id': len(placed),
                                'original': (tw, th),
                            })
                            trim_x += tpiece_w + self.kerf

            current_y += row['height']

        print(f"  → {len(placed)}개 조각 배치 성공 ({len(region['rows'])}개 행)")

        # placed_w/h 설정 (회전 반영된 실제 크기 — 후속 subtree 빌드가 소비)
        for piece in placed:
            if piece.get('rotated', False):
                piece['placed_w'] = piece['height']
                piece['placed_h'] = piece['width']
            else:
                piece['placed_w'] = piece['width']
                piece['placed_h'] = piece['height']

        # max_height는 호출측 스키마 정합성을 위해 참조만 해두고 사용 안 함.
        _ = max_height

        return placed

    def _init_region_occupancy(self, regions: list[dict]) -> None:
        """Phase A 결과물에 `occupied`/`free_rects` 필드를 추가.

        Region 좌표계(region.x/y 원점)로 앵커 그룹의 조각 bounding box를
        기록한다. **stacked 그룹은 count개의 Rect로 따로 기록** — 이것이
        P0 버그(stacked 위에 덮어쓰기)의 근본 수정 지점. 한 덩어리가 아닌
        여러 Rect로 표현되므로 이후 패스가 그 사이에 조각을 끼워넣을 수 없다.

        이 단계에서 `free_rects`는 간단한 행-기반 분할로 채운다:
          - 비-stacked 그룹 위의 trim 스트립 (앵커보다 낮은 그룹 위 빈 공간)
          - 모든 그룹의 오른쪽 남은 공간
          - 행 아래 여분(일반적으로 0)

        호출 시점: Phase A 직후, Phase B(`_optimize_trim_placement`) 직전.
        이 단계는 필드만 추가하고 기존 동작에는 영향 없다(아직 읽는 패스 없음).
        """
        for region in regions:
            occupied: list[Rect] = []
            free_rects: list[Rect] = []

            rows = region.get('rows') or []
            row_height = rows[0]['height'] if rows else 0
            groups = rows[0]['groups'] if rows else []

            # 앵커 그룹 조각들을 occupied에 기록
            current_x = 0
            for group in groups:
                ow, oh = group['original_size']
                rotated = group['rotated']
                stacked = group.get('stacked', False)
                piece_w = oh if rotated else ow
                piece_h = ow if rotated else oh
                count = group['count']

                if stacked:
                    # 한 컬럼에 count개 세로로 쌓음 — 조각마다 별도 Rect
                    for i in range(count):
                        occupied.append(Rect(
                            current_x,
                            i * (piece_h + self.kerf),
                            piece_w,
                            piece_h,
                        ))
                    current_x += piece_w + self.kerf
                else:
                    for i in range(count):
                        occupied.append(Rect(
                            current_x + i * (piece_w + self.kerf),
                            0,
                            piece_w,
                            piece_h,
                        ))
                    current_x += (piece_w + self.kerf) * count

            # free_rects: 각 그룹 위 trim 스트립 + 우측 여백 + 아래 여분
            scan_x = 0
            for group in groups:
                ow, oh = group['original_size']
                rotated = group['rotated']
                stacked = group.get('stacked', False)
                piece_w = oh if rotated else ow
                piece_h = ow if rotated else oh
                count = group['count']

                group_w = (
                    piece_w
                    if stacked
                    else (piece_w + self.kerf) * count - self.kerf
                )

                # 비-stacked 그룹이 앵커보다 낮으면 위에 trim 스트립
                if not stacked and row_height > piece_h + self.kerf:
                    trim_y = piece_h + self.kerf
                    free_rects.append(Rect(
                        scan_x, trim_y, group_w, row_height - trim_y,
                    ))

                scan_x += group_w + self.kerf

            # 그룹 우측 여백
            groups_end_x = scan_x - self.kerf if groups else 0
            right_x = groups_end_x + self.kerf if groups else 0
            if region['width'] > right_x:
                free_rects.append(Rect(
                    right_x, 0,
                    region['width'] - right_x, row_height,
                ))

            # 행 아래 여분 (일반적으로 0이지만 방어적으로)
            if region['height'] > row_height:
                free_rects.append(Rect(
                    0, row_height,
                    region['width'], region['height'] - row_height,
                ))

            region['occupied'] = occupied
            region['free_rects'] = free_rects

    def _optimize_trim_placement(self, regions: list[dict]) -> None:
        """이후 영역 그룹을 이전 영역 trim 공간으로 재배치 (최적화)

        백트래킹으로 확정된 regions에서 이후 영역의 소형 그룹을
        이전 영역의 trim 공간으로 이동하여 판재 활용도를 높임.
        빈 영역은 scrap으로 전환.

        Args:
            regions: _allocate_anchor_backtrack()의 결과 (in-place 수정)
        """
        for i, region in enumerate(regions):
            if region.get('type') == 'scrap':
                continue

            row = region['rows'][0]
            row_height = row['height']
            current_x = region['x']

            for group in row['groups']:
                w, h = group['original_size']
                rotated = group['rotated']
                piece_w = h if rotated else w
                piece_h = w if rotated else h
                stacked = group.get('stacked', False)

                group_start_x = current_x

                # current_x 업데이트 (다음 그룹 시작점 추적)
                if stacked:
                    current_x += piece_w + self.kerf
                else:
                    current_x += (piece_w + self.kerf) * group['count']

                # stacked 그룹은 column 전체를 점유하므로 "위에 trim 공간" 개념이
                # 성립하지 않는다. row_height - piece_h 는 두 번째 stacked 조각의
                # 영역이며 빈 공간이 아니다 (P0 겹침 버그의 근본 원인).
                if stacked:
                    continue

                # kerf 2개: 주조각↔trim 사이 + trim↔영역경계 사이
                trim_height = row_height - piece_h - 2 * self.kerf
                if trim_height < self.kerf:
                    continue

                # 같은 행에 "중간 높이" 그룹이 있으면 skip
                # 앵커(최대 높이)의 H컷은 trim 끝과 정확히 일치하므로 무해하지만,
                # piece_h < G < row_height - kerf 인 그룹의 H컷은 trim 공간 내부를 관통함
                if any(
                    piece_h < (g['original_size'][0] if g['rotated'] else g['original_size'][1]) < row_height - self.kerf
                    for g in row['groups'] if g is not group
                ):
                    continue

                # trim strip: 오른쪽으로 더 키 큰 그룹이 나타나기 전까지 확장
                # (더 키 큰 그룹은 trim_y 높이까지 조각이 있어서 공간이 막힘)
                trim_x_end = region['x'] + region['width']
                scan_x = current_x  # 현재 그룹 다음 위치부터 스캔
                current_group_idx = row['groups'].index(group)
                for rg in row['groups'][current_group_idx + 1:]:
                    rw, rh = rg['original_size']
                    rrotated = rg['rotated']
                    rpiece_w = rh if rrotated else rw
                    rpiece_h = rw if rrotated else rh
                    if rpiece_h > piece_h:  # 더 키 큰 그룹이 trim 공간을 막음
                        trim_x_end = scan_x
                        break
                    if rg.get('stacked', False):
                        scan_x += rpiece_w + self.kerf
                    else:
                        scan_x += (rpiece_w + self.kerf) * rg['count']
                trim_width_available = trim_x_end - group_start_x

                # 후보 수집: 이후 region의 잔여 그룹을 평탄화
                candidates = self._collect_trim_candidates(regions, i + 1)
                if not candidates:
                    continue

                # Shelf 기반 백트래킹: greedy FFDH lower bound + DFS with pruning.
                # shelf 동질성(같은 height만 병합)을 강제해 cut 생성은 무변경.
                shelves = self._pack_strip_shelves(
                    trim_width_available, trim_height, candidates, self.kerf,
                )
                if not shelves:
                    continue

                # trim_rows 엔트리 변환 + 후보 count 감소 + 점유 방어 assert
                self._apply_shelf_result(
                    group, shelves, candidates,
                    piece_h, region, group_start_x, i, regions,
                )

        # 연속된 scrap 영역 병합 (불필요한 경계 절단선 제거)
        i = 0
        while i < len(regions) - 1:
            if regions[i].get('type') == 'scrap' and regions[i + 1].get('type') == 'scrap':
                regions[i]['height'] += regions[i + 1]['height']
                regions.pop(i + 1)
            else:
                i += 1

    def _collect_trim_candidates(self, regions: list[dict], start_idx: int) -> list[dict]:
        """regions[start_idx..]의 잔여 그룹을 trim 후보로 평탄화.

        각 후보는 {region_idx, group_ref, original_size, rotated, piece_w, piece_h,
        count}. group_ref 는 source region의 group dict를 그대로 참조하므로
        `_apply_shelf_result` 에서 count를 직접 감소시킬 수 있다.
        """
        candidates: list[dict] = []
        for ridx in range(start_idx, len(regions)):
            r = regions[ridx]
            if r.get('type') == 'scrap':
                continue
            rows = r.get('rows') or []
            if not rows:
                continue
            for g in rows[0]['groups']:
                if g.get('count', 0) <= 0:
                    continue
                ow, oh = g['original_size']
                rot = g['rotated']
                candidates.append({
                    'region_idx': ridx,
                    'group_ref': g,
                    'original_size': (ow, oh),
                    'rotated': rot,
                    'piece_w': oh if rot else ow,
                    'piece_h': ow if rot else oh,
                    'count': g['count'],
                })
        return candidates

    def _pack_strip_shelves(
        self,
        strip_w: int,
        strip_h: int,
        candidates: list[dict],
        kerf: int,
    ) -> list[dict]:
        """Strip(strip_w × strip_h)을 shelf 기반으로 2D 패킹.

        Shelf 구조:
          - 각 shelf는 y_offset + height (동일 높이 조각만 수용) + 좌측부터 순차 배치
          - strip 내 shelf 여러 개 허용: y = 0, h0+kerf, h0+kerf+h1+kerf, ...
          - "한 줄 우선": 기존 shelf 확장을 새 shelf 생성보다 먼저 시도

        탐색:
          1. 후보를 unit-level로 펼쳐 면적-desc 고정 순서로 정렬
          2. Greedy FFDH로 초기 lower bound 확보
          3. DFS로 백트래킹 — 각 유닛을 "기존 shelf (동일 높이, 폭 맞음) | 새 shelf"
             중 하나에 배치. place 가능하면 skip 분기 없음 (면적 desc 정렬에서
             place 는 skip 을 지배). 가지치기: current + 잔여_면적_상한 ≤ best.
          4. 최고 점수의 shelf 리스트 반환. 동점은 조각 수로 tie-break.

        Returns: list of {'y', 'height', 'pieces': [(cand_idx, piece_w, piece_h), ...]}.
        pieces 순서 = shelf 내 좌측→우측.
        """
        if not candidates or strip_w <= 0 or strip_h <= 0:
            return []

        # Unit 전개 (같은 후보의 count 개 만큼 index 반복)
        units: list[int] = []
        for idx, c in enumerate(candidates):
            if c['piece_h'] > strip_h or c['piece_w'] > strip_w:
                continue
            units.extend([idx] * c['count'])
        if not units:
            return []

        # 면적 desc, tie-break: 높이 desc → 너비 desc
        units.sort(key=lambda i: (
            -(candidates[i]['piece_w'] * candidates[i]['piece_h']),
            -candidates[i]['piece_h'],
            -candidates[i]['piece_w'],
        ))

        # 잔여 면적 접미합 (가지치기용 낙관적 상한)
        suffix_area = [0] * (len(units) + 1)
        for i in range(len(units) - 1, -1, -1):
            c = candidates[units[i]]
            suffix_area[i] = suffix_area[i + 1] + c['piece_w'] * c['piece_h']

        # 1) Greedy FFDH baseline (shelf 동질성 제약)
        baseline = self._greedy_shelves(strip_w, strip_h, units, candidates, kerf)
        best_area = sum(p[1] * p[2] for s in baseline for p in s['pieces'])
        best_count = sum(len(s['pieces']) for s in baseline)
        best_snapshot = [
            {'y': s['y'], 'height': s['height'], 'pieces': list(s['pieces'])}
            for s in baseline
        ]

        # 2) DFS 백트래킹
        def dfs(i: int, shelves: list[dict], current_area: int) -> None:
            nonlocal best_area, best_count, best_snapshot

            count_so_far = sum(len(s['pieces']) for s in shelves)
            if current_area > best_area or (
                current_area == best_area and count_so_far > best_count
            ):
                best_area = current_area
                best_count = count_so_far
                best_snapshot = [
                    {'y': s['y'], 'height': s['height'], 'pieces': list(s['pieces'])}
                    for s in shelves
                ]

            if i == len(units):
                return

            # 가지치기: 지금까지 + 잔여 전체 면적도 best에 못 미치면 컷
            if current_area + suffix_area[i] < best_area:
                return

            u_idx = units[i]
            cand = candidates[u_idx]
            pw, ph = cand['piece_w'], cand['piece_h']
            placed_any = False

            # (i) 기존 shelf 확장 — 동일 높이만, 너비 체크
            for s in shelves:
                if s['height'] != ph:
                    continue
                needed = pw if not s['pieces'] else pw + kerf
                if s['x_used'] + needed > strip_w:
                    continue
                saved_x = s['x_used']
                s['x_used'] = saved_x + needed
                s['pieces'].append((u_idx, pw, ph))
                dfs(i + 1, shelves, current_area + pw * ph)
                s['pieces'].pop()
                s['x_used'] = saved_x
                placed_any = True

            # (ii) 새 shelf 생성 — strip 높이 잔여 확인
            if shelves:
                next_y = sum(s['height'] for s in shelves) + len(shelves) * kerf
            else:
                next_y = 0
            if next_y + ph <= strip_h and pw <= strip_w:
                new_shelf = {
                    'y': next_y, 'height': ph, 'x_used': pw,
                    'pieces': [(u_idx, pw, ph)],
                }
                shelves.append(new_shelf)
                dfs(i + 1, shelves, current_area + pw * ph)
                shelves.pop()
                placed_any = True

            # (iii) 배치 불가 → 해당 유닛 skip하고 진행
            if not placed_any:
                dfs(i + 1, shelves, current_area)

        dfs(0, [], 0)

        # 반환 전 x_used 제거 (결과 소비자는 불필요)
        for s in best_snapshot:
            s.pop('x_used', None)
        return best_snapshot

    def _greedy_shelves(
        self,
        strip_w: int,
        strip_h: int,
        units: list[int],
        candidates: list[dict],
        kerf: int,
    ) -> list[dict]:
        """FFDH 유사 shelf 패킹 — 동일 height shelf만 확장, 아니면 새 shelf.

        백트래킹의 초기 lower bound 공급용. 결정론적 greedy.
        """
        shelves: list[dict] = []
        for u_idx in units:
            c = candidates[u_idx]
            pw, ph = c['piece_w'], c['piece_h']
            placed = False
            for s in shelves:
                if s['height'] != ph:
                    continue
                needed = pw if not s['pieces'] else pw + kerf
                if s['x_used'] + needed <= strip_w:
                    s['x_used'] += needed
                    s['pieces'].append((u_idx, pw, ph))
                    placed = True
                    break
            if placed:
                continue
            next_y = (
                sum(s['height'] for s in shelves) + len(shelves) * kerf
                if shelves else 0
            )
            if next_y + ph <= strip_h and pw <= strip_w:
                shelves.append({
                    'y': next_y, 'height': ph, 'x_used': pw,
                    'pieces': [(u_idx, pw, ph)],
                })
        return shelves

    def _apply_shelf_result(
        self,
        anchor_group: dict,
        shelves: list[dict],
        candidates: list[dict],
        piece_h: int,
        region: dict,
        group_start_x: int,
        region_idx: int,
        regions: list[dict],
    ) -> None:
        """Shelf 결과를 anchor_group.trim_rows + 후보 count 감소 + 방어 assert 로 반영.

        - 각 shelf → 하나의 trim_rows 엔트리 (y_offset, height, groups)
        - shelf 내 동일 cand_idx 연속은 하나의 trim_group 으로 병합
        - 후보 candidates[u_idx]['group_ref']['count'] -= 배치된 수
        - 각 배치 직전 region['occupied']와 Rect 교차 검사 — 겹침 시 AssertionError
        - 완료 후 count=0 이 된 그룹을 source region row에서 제거,
          row가 비면 region을 scrap 전환
        """
        kerf = self.kerf
        occupied_rects = region.get('occupied', [])

        # trim_rows 엔트리 생성 + 방어 검사
        for shelf in shelves:
            trim_groups: list[dict] = []
            cursor_x_local = group_start_x - region['x']
            y_local = piece_h + kerf + shelf['y']
            last_cand_idx: int | None = None

            for (u_idx, pw, ph) in shelf['pieces']:
                cand = candidates[u_idx]
                candidate_rect = Rect(cursor_x_local, y_local, pw, ph)
                for occ in occupied_rects:
                    if intersects(candidate_rect, occ):
                        raise AssertionError(
                            f"trim 배치가 점유 공간과 겹침: "
                            f"cand={candidate_rect}, occ={occ}, "
                            f"region=({region['x']},{region['y']},"
                            f"{region['width']}×{region['height']})"
                        )
                if last_cand_idx == u_idx and trim_groups:
                    trim_groups[-1]['count'] += 1
                else:
                    trim_groups.append({
                        'original_size': cand['original_size'],
                        'rotated': cand['rotated'],
                        'count': 1,
                    })
                    last_cand_idx = u_idx
                cursor_x_local += pw + kerf

            if not trim_groups:
                continue

            anchor_group.setdefault('trim_rows', []).append({
                'y_offset': piece_h + kerf + shelf['y'],
                'groups': trim_groups,
                'height': shelf['height'],
            })
            moved_sig = ', '.join(
                f"{tg['original_size'][0]}×{tg['original_size'][1]}×{tg['count']}"
                for tg in trim_groups
            )
            print(
                f"  [trim 최적화] shelf y={shelf['y']} h={shelf['height']}: {moved_sig} "
                f"→ R{region_idx+1}"
            )

        # 후보 count 감소 (group_ref 직접 수정)
        for shelf in shelves:
            for (u_idx, _pw, _ph) in shelf['pieces']:
                g = candidates[u_idx]['group_ref']
                g['count'] -= 1
                if g['count'] < 0:
                    raise AssertionError(f"후보 count 음수: {g}")

        # count=0 그룹 제거 + 빈 row → scrap 전환
        touched_regions = {candidates[u_idx]['region_idx']
                           for s in shelves for (u_idx, _, _) in s['pieces']}
        for ridx in touched_regions:
            r = regions[ridx]
            if r.get('type') == 'scrap':
                continue
            row = r['rows'][0]
            row['groups'] = [g for g in row['groups'] if g['count'] > 0]
            if not row['groups']:
                r['type'] = 'scrap'
                r['rows'] = [{'groups': [], 'height': 0}]

    def _allocate_mixed_regions(self, height_clusters, width_clusters, strategy='horizontal_first'):
        """높이 기반 + 너비 기반 클러스터를 혼합하여 영역 할당

        Args:
            height_clusters: 높이 기반 클러스터 리스트
            width_clusters: 너비 기반 클러스터 리스트
            strategy: 영역 할당 전략
                - 'horizontal_only': 수평 영역만 (다단 구조)
                - 'horizontal_first': 수평 영역 우선 (상하 쌓기 → 좌우 나누기)
                - 'vertical_first': 수직 영역 우선 (좌우 나누기 → 상하 쌓기)
                - 'mixed': 수평/수직 번갈아 배치 (면적순)

        Returns:
            List of regions
        """
        if strategy == 'horizontal_only':
            return self._allocate_horizontal_only(height_clusters, width_clusters)
        elif strategy == 'horizontal_first':
            return self._allocate_horizontal_first(height_clusters, width_clusters)
        elif strategy == 'vertical_first':
            return self._allocate_vertical_first(height_clusters, width_clusters)
        elif strategy == 'mixed':
            return self._allocate_mixed_interleaved(height_clusters, width_clusters)
        else:
            return self._allocate_horizontal_first(height_clusters, width_clusters)

    def _allocate_horizontal_only(self, height_clusters, width_clusters):
        """수평 영역만 전략: 높이 클러스터를 다단 구조로 배치

        핵심: 영역 높이를 조각들이 실제 차지할 공간으로 동적 계산
        """
        import math

        regions = []
        used_groups = set()
        current_y = 0

        # 높이 클러스터만 사용 (면적순 정렬)
        sorted_clusters = sorted(height_clusters, key=lambda c: c['total_area'], reverse=True)

        for cluster in sorted_clusters:
            # 중복 그룹 제거
            unique_groups = []
            for group in cluster['groups']:
                group_key = (group['size'], group['rotated'])
                if group_key not in used_groups:
                    unique_groups.append(group)
                    used_groups.add(group_key)

            if not unique_groups:
                continue

            # 총 조각 수 계산
            total_pieces = sum(g['count'] for g in unique_groups)

            # 가장 큰 조각의 너비 계산 (회전 고려)
            max_width = 0
            for group in unique_groups:
                w, h = group['size']
                piece_w = h if group['rotated'] else w
                max_width = max(max_width, piece_w)

            # 1행당 배치 가능한 조각 수
            pieces_per_row = self.plate_width // (max_width + self.kerf)

            if pieces_per_row == 0:
                continue  # 조각이 너무 큼

            # 필요한 행 수
            rows_needed = math.ceil(total_pieces / pieces_per_row)

            # 영역 높이 = 행 수 × (조각 높이 + kerf)
            region_height = rows_needed * (cluster['dimension_value'] + self.kerf)

            if current_y + region_height <= self.plate_height:
                regions.append({
                    'type': 'horizontal',
                    'x': 0,
                    'y': current_y,
                    'width': self.plate_width,
                    'height': region_height,
                    'cluster': cluster,
                    'groups': unique_groups
                })
                current_y += region_height

        return regions

    def _allocate_horizontal_first(self, height_clusters, width_clusters):
        """수평 영역 우선 전략: 수평 먼저 (상하 쌓기) → 수직 나중 (좌우 나누기)"""
        used_groups = set()

        all_clusters = []
        for cluster in height_clusters:
            all_clusters.append(('horizontal', cluster))
        for cluster in width_clusters:
            all_clusters.append(('vertical', cluster))

        all_clusters.sort(key=lambda x: x[1]['total_area'], reverse=True)

        # 1단계: 수평 영역 (상하로 쌓기)
        current_y = 0
        horizontal_regions = []

        for region_type, cluster in all_clusters:
            if region_type != 'horizontal':
                continue

            unique_groups = []
            for group in cluster['groups']:
                group_key = (group['size'], group['rotated'])
                if group_key not in used_groups:
                    unique_groups.append(group)
                    used_groups.add(group_key)

            if not unique_groups:
                continue

            region_height = cluster['dimension_value'] + self.kerf

            if current_y + region_height <= self.plate_height:
                horizontal_regions.append({
                    'type': 'horizontal',
                    'x': 0,
                    'y': current_y,
                    'width': self.plate_width,
                    'height': region_height,
                    'cluster': cluster,
                    'groups': unique_groups
                })
                current_y += region_height

        # 2단계: 수직 영역 (좌우로 나누기) - 남은 공간
        vertical_regions = []
        current_x = 0
        remaining_height = self.plate_height - current_y

        for region_type, cluster in all_clusters:
            if region_type != 'vertical':
                continue

            unique_groups = []
            for group in cluster['groups']:
                group_key = (group['size'], group['rotated'])
                if group_key not in used_groups:
                    unique_groups.append(group)
                    used_groups.add(group_key)

            if not unique_groups:
                continue

            region_width = cluster['dimension_value'] + self.kerf

            if current_x + region_width <= self.plate_width and remaining_height > 0:
                vertical_regions.append({
                    'type': 'vertical',
                    'x': current_x,
                    'y': current_y,
                    'width': region_width,
                    'height': remaining_height,
                    'cluster': cluster,
                    'groups': unique_groups
                })
                current_x += region_width

        return horizontal_regions + vertical_regions

    def _allocate_vertical_first(self, height_clusters, width_clusters):
        """수직 영역 우선 전략: 수직 먼저 (좌우 나누기) → 수평 나중 (상하 쌓기)"""
        used_groups = set()

        all_clusters = []
        for cluster in height_clusters:
            all_clusters.append(('horizontal', cluster))
        for cluster in width_clusters:
            all_clusters.append(('vertical', cluster))

        all_clusters.sort(key=lambda x: x[1]['total_area'], reverse=True)

        # 1단계: 수직 영역 (좌우로 나누기)
        current_x = 0
        vertical_regions = []

        for region_type, cluster in all_clusters:
            if region_type != 'vertical':
                continue

            unique_groups = []
            for group in cluster['groups']:
                group_key = (group['size'], group['rotated'])
                if group_key not in used_groups:
                    unique_groups.append(group)
                    used_groups.add(group_key)

            if not unique_groups:
                continue

            region_width = cluster['dimension_value'] + self.kerf

            if current_x + region_width <= self.plate_width:
                vertical_regions.append({
                    'type': 'vertical',
                    'x': current_x,
                    'y': 0,
                    'width': region_width,
                    'height': self.plate_height,
                    'cluster': cluster,
                    'groups': unique_groups
                })
                current_x += region_width

        # 2단계: 수평 영역 (상하로 쌓기) - 남은 공간
        horizontal_regions = []
        current_y = 0
        remaining_width = self.plate_width - current_x

        for region_type, cluster in all_clusters:
            if region_type != 'horizontal':
                continue

            unique_groups = []
            for group in cluster['groups']:
                group_key = (group['size'], group['rotated'])
                if group_key not in used_groups:
                    unique_groups.append(group)
                    used_groups.add(group_key)

            if not unique_groups:
                continue

            region_height = cluster['dimension_value'] + self.kerf

            if current_y + region_height <= self.plate_height and remaining_width > 0:
                horizontal_regions.append({
                    'type': 'horizontal',
                    'x': current_x,
                    'y': current_y,
                    'width': remaining_width,
                    'height': region_height,
                    'cluster': cluster,
                    'groups': unique_groups
                })
                current_y += region_height

        return vertical_regions + horizontal_regions

    def _allocate_mixed_interleaved(self, height_clusters, width_clusters):
        """혼합 전략: 수평/수직 영역을 면적순으로 번갈아 배치"""
        regions = []
        used_groups = set()

        all_clusters = []
        for cluster in height_clusters:
            all_clusters.append(('horizontal', cluster))
        for cluster in width_clusters:
            all_clusters.append(('vertical', cluster))

        all_clusters.sort(key=lambda x: x[1]['total_area'], reverse=True)

        current_x = 0
        current_y = 0

        for region_type, cluster in all_clusters:
            unique_groups = []
            for group in cluster['groups']:
                group_key = (group['size'], group['rotated'])
                if group_key not in used_groups:
                    unique_groups.append(group)
                    used_groups.add(group_key)

            if not unique_groups:
                continue

            if region_type == 'horizontal':
                # 수평 영역 (상하로 쌓기)
                region_height = cluster['dimension_value'] + self.kerf

                if current_y + region_height <= self.plate_height:
                    regions.append({
                        'type': 'horizontal',
                        'x': 0,
                        'y': current_y,
                        'width': self.plate_width,
                        'height': region_height,
                        'cluster': cluster,
                        'groups': unique_groups
                    })
                    current_y += region_height

            else:  # 'vertical'
                # 수직 영역 (좌우로 나누기)
                region_width = cluster['dimension_value'] + self.kerf
                remaining_height = self.plate_height - current_y

                if current_x + region_width <= self.plate_width and remaining_height > 0:
                    regions.append({
                        'type': 'vertical',
                        'x': current_x,
                        'y': current_y,
                        'width': region_width,
                        'height': remaining_height,
                        'cluster': cluster,
                        'groups': unique_groups
                    })
                    current_x += region_width

        return regions

    def _allocate_simple_greedy(self, height_clusters, width_clusters):
        """단순 탐욕 전략: 수평 영역 우선, 남은 공간에 수직 영역"""
        # horizontal_first와 동일하게 수정
        return self._allocate_horizontal_first(height_clusters, width_clusters)

    def _allocate_recursive_2d(self, height_clusters, width_clusters):
        """재귀적 2D 분할 전략: 백트래킹으로 최적 영역 조합 탐색

        핵심 아이디어:
        - 각 그룹에 대해 4가지 선택지를 백트래킹으로 탐색:
          1. 회전 안함 + 높이 기반 배치 (horizontal)
          2. 회전 안함 + 너비 기반 배치 (vertical)
          3. 회전 함 + 높이 기반 배치 (horizontal)
          4. 회전 함 + 너비 기반 배치 (vertical)
        - 각 그룹은 정확히 한 번만 배치
        - Guillotine 제약을 만족하도록 영역 생성
        """
        # 1. 모든 고유 그룹 추출 (중복 제거)
        all_groups_dict = {}  # key: (width, height), value: count

        for cluster in height_clusters:
            for group in cluster['groups']:
                size = group['size']
                if size not in all_groups_dict:
                    all_groups_dict[size] = group['count']

        for cluster in width_clusters:
            for group in cluster['groups']:
                size = group['size']
                if size not in all_groups_dict:
                    all_groups_dict[size] = group['count']

        # 2. 각 그룹에 대해 4가지 클러스터 옵션 생성
        group_options = []

        for size, count in all_groups_dict.items():
            w, h = size

            # 옵션 1: 회전 안함 + 높이 기반 (horizontal)
            group_options.append({
                'original_size': size,
                'rotated': False,
                'cluster_type': 'horizontal',
                'dimension_value': h,  # 높이 기반
                'count': count,
                'total_area': w * h * count
            })

            # 옵션 2: 회전 안함 + 너비 기반 (vertical)
            group_options.append({
                'original_size': size,
                'rotated': False,
                'cluster_type': 'vertical',
                'dimension_value': w,  # 너비 기반
                'count': count,
                'total_area': w * h * count
            })

            if self.allow_rotation:
                # 옵션 3: 회전 함 + 높이 기반 (horizontal)
                group_options.append({
                    'original_size': size,
                    'rotated': True,
                    'cluster_type': 'horizontal',
                    'dimension_value': w,  # 회전 후 높이 = 원래 너비
                    'count': count,
                    'total_area': w * h * count
                })

                # 옵션 4: 회전 함 + 너비 기반 (vertical)
                group_options.append({
                    'original_size': size,
                    'rotated': True,
                    'cluster_type': 'vertical',
                    'dimension_value': h,  # 회전 후 너비 = 원래 높이
                    'count': count,
                    'total_area': w * h * count
                })

        # 3. 면적순 정렬 (큰 그룹 우선)
        group_options.sort(key=lambda x: x['total_area'], reverse=True)

        num_groups = len(all_groups_dict)  # 총 그룹 개수

        # 4. 백트래킹을 위한 재귀 함수
        def backtrack(regions_so_far, used_original_sizes):
            """재귀적 백트래킹으로 영역 할당

            Args:
                regions_so_far: 지금까지 생성된 영역들
                used_original_sizes: 이미 사용된 원본 크기들 (중복 배치 방지)

            Returns:
                (최선의 영역 리스트, 배치 가능한 조각 수)
            """
            if len(used_original_sizes) == num_groups:
                # 모든 그룹 할당 완료
                piece_count = sum(sum(g['count'] for g in r['groups']) for r in regions_so_far)
                return regions_so_far, piece_count

            best_regions = regions_so_far
            best_count = sum(sum(g['count'] for g in r['groups']) for r in regions_so_far)

            # 각 옵션을 시도
            for option in group_options:
                original_size = option['original_size']

                # 이 그룹이 이미 사용되었으면 스킵
                if original_size in used_original_sizes:
                    continue

                # 클러스터 생성 (단일 그룹)
                cluster = {
                    'dimension_value': option['dimension_value'],
                    'groups': [{
                        'size': original_size,
                        'rotated': option['rotated'],
                        'count': option['count']
                    }],
                    'total_area': option['total_area']
                }

                # 이 클러스터를 배치할 수 있는 모든 위치 탐색
                possible_placements = self._find_region_placements(
                    regions_so_far, option['cluster_type'], cluster, cluster['groups']
                )

                if not possible_placements:
                    # 배치 불가능 - 스킵
                    continue

                for placement in possible_placements:
                    # 새 영역 추가
                    new_regions = regions_so_far + [placement]
                    new_used = used_original_sizes | {original_size}

                    # 재귀적으로 남은 옵션 배치
                    result_regions, result_count = backtrack(
                        new_regions,
                        new_used
                    )

                    if result_count > best_count:
                        best_count = result_count
                        best_regions = result_regions

            return best_regions, best_count

        # 백트래킹 시작
        print(f"\n[백트래킹 디버그] 총 {num_groups}개 그룹, {len(group_options)}개 옵션")
        regions, count = backtrack([], set())
        print(f"[백트래킹 완료] {count}개 조각 배치, {len(regions)}개 영역")

        return regions

    def _find_region_placements(self, existing_regions, region_type, cluster, unique_groups):
        """주어진 클러스터를 배치할 수 있는 모든 위치 찾기

        Returns:
            가능한 영역 배치 리스트
        """
        import math

        placements = []

        # 현재 사용 중인 공간 계산
        if not existing_regions:
            # 첫 영역: 전체 판 사용 가능
            free_rects = [(0, 0, self.plate_width, self.plate_height)]
        else:
            # 기존 영역들로부터 자유 공간 계산
            free_rects = self._calculate_free_rects(existing_regions)

        # 각 자유 공간에 배치 시도
        for x, y, w, h in free_rects:
            if region_type == 'horizontal':
                # 수평 영역: 높이는 고정, 너비는 실제 필요한 만큼만
                region_height = cluster['dimension_value'] + self.kerf

                if region_height > h:
                    continue

                # 총 조각 수 계산
                total_pieces = sum(g['count'] for g in unique_groups)

                # 가장 큰 조각의 너비 계산 (회전 고려)
                max_piece_width = 0
                for group in unique_groups:
                    gw, gh = group['size']
                    piece_w = gh if group['rotated'] else gw
                    max_piece_width = max(max_piece_width, piece_w)

                # 1행당 배치 가능한 조각 수
                pieces_per_row = w // (max_piece_width + self.kerf)

                if pieces_per_row == 0:
                    continue

                # 필요한 행 수
                rows_needed = math.ceil(total_pieces / pieces_per_row)

                # 실제 필요한 너비 계산
                pieces_in_first_row = min(total_pieces, pieces_per_row)
                required_width = pieces_in_first_row * (max_piece_width + self.kerf)

                # 자유 공간보다 작거나 같으면 배치 가능
                if required_width <= w and rows_needed * region_height <= h:
                    # 여러 위치 옵션 생성 (왼쪽, 가운데, 오른쪽)
                    positions = [(x, y)]  # 기본: 왼쪽 정렬

                    # 가운데 정렬 (공간이 남으면)
                    if w > required_width:
                        center_x = x + (w - required_width) // 2
                        if center_x != x:
                            positions.append((center_x, y))

                    # 오른쪽 정렬 (공간이 남으면)
                    if w > required_width:
                        right_x = x + w - required_width
                        if right_x != x and (len(positions) < 2 or right_x != positions[1][0]):
                            positions.append((right_x, y))

                    for px, py in positions:
                        placements.append({
                            'type': 'horizontal',
                            'x': px,
                            'y': py,
                            'width': required_width,
                            'height': rows_needed * region_height,
                            'cluster': cluster,
                            'groups': unique_groups
                        })

            else:  # 'vertical'
                # 수직 영역: 너비는 고정, 높이는 실제 필요한 만큼만
                region_width = cluster['dimension_value'] + self.kerf

                if region_width > w:
                    continue

                # 총 조각 수 계산
                total_pieces = sum(g['count'] for g in unique_groups)

                # 가장 큰 조각의 높이 계산 (회전 고려)
                max_piece_height = 0
                for group in unique_groups:
                    gw, gh = group['size']
                    piece_h = gw if group['rotated'] else gh
                    max_piece_height = max(max_piece_height, piece_h)

                # 1열당 배치 가능한 조각 수
                pieces_per_col = h // (max_piece_height + self.kerf)

                if pieces_per_col == 0:
                    continue

                # 필요한 열 수
                cols_needed = math.ceil(total_pieces / pieces_per_col)

                # 실제 필요한 높이 계산
                pieces_in_first_col = min(total_pieces, pieces_per_col)
                required_height = pieces_in_first_col * (max_piece_height + self.kerf)

                # 자유 공간보다 작거나 같으면 배치 가능
                if cols_needed * region_width <= w and required_height <= h:
                    # 여러 위치 옵션 생성 (위쪽, 가운데, 아래쪽)
                    positions = [(x, y)]  # 기본: 위쪽 정렬

                    # 가운데 정렬 (공간이 남으면)
                    if h > required_height:
                        center_y = y + (h - required_height) // 2
                        if center_y != y:
                            positions.append((x, center_y))

                    # 아래쪽 정렬 (공간이 남으면)
                    if h > required_height:
                        bottom_y = y + h - required_height
                        if bottom_y != y and (len(positions) < 2 or bottom_y != positions[1][1]):
                            positions.append((x, bottom_y))

                    for px, py in positions:
                        placements.append({
                            'type': 'vertical',
                            'x': px,
                            'y': py,
                            'width': cols_needed * region_width,
                            'height': required_height,
                            'cluster': cluster,
                            'groups': unique_groups
                        })

        return placements

    def _calculate_free_rects(self, regions):
        """기존 영역들로부터 남은 자유 공간(rectangles) 계산

        Maximal Rectangles 알고리즘 사용
        """
        if not regions:
            return [(0, 0, self.plate_width, self.plate_height)]

        # 모든 영역의 경계 좌표 수집
        x_coords = {0, self.plate_width}
        y_coords = {0, self.plate_height}

        for r in regions:
            x_coords.add(r['x'])
            x_coords.add(r['x'] + r['width'])
            y_coords.add(r['y'])
            y_coords.add(r['y'] + r['height'])

        x_coords = sorted(x_coords)
        y_coords = sorted(y_coords)

        # 모든 가능한 직사각형 생성
        free_rects = []

        for i in range(len(x_coords) - 1):
            for j in range(len(y_coords) - 1):
                x1, x2 = x_coords[i], x_coords[i + 1]
                y1, y2 = y_coords[j], y_coords[j + 1]

                # 이 직사각형이 기존 영역과 겹치는지 확인
                is_free = True
                for r in regions:
                    rx1, rx2 = r['x'], r['x'] + r['width']
                    ry1, ry2 = r['y'], r['y'] + r['height']

                    # 겹침 검사
                    if not (x2 <= rx1 or x1 >= rx2 or y2 <= ry1 or y1 >= ry2):
                        is_free = False
                        break

                if is_free:
                    free_rects.append((x1, y1, x2 - x1, y2 - y1))

        # 최대 직사각형만 유지 (다른 직사각형에 포함되지 않는 것)
        maximal_rects = []
        for rect in free_rects:
            x1, y1, w1, h1 = rect
            is_maximal = True

            for other in free_rects:
                if rect == other:
                    continue
                x2, y2, w2, h2 = other

                # rect가 other에 완전히 포함되면 maximal이 아님
                if x2 <= x1 and y2 <= y1 and x2 + w2 >= x1 + w1 and y2 + h2 >= y1 + h1:
                    is_maximal = False
                    break

            if is_maximal and w1 > 0 and h1 > 0:
                maximal_rects.append(rect)

        return maximal_rects if maximal_rects else []

    def _pack_region(self, region):
        """특정 영역 내에서 조각들 배치 (그룹 기반, 다단 배치)

        Args:
            region: _allocate_mixed_regions()가 생성한 영역 정보

        Returns:
            배치된 조각 리스트 또는 None (실패 시)
        """
        groups = region['groups']  # [그룹들]
        region_x = region['x']
        region_y = region['y']
        region_w = region['width']
        region_h = region['height']

        # 영역 크기로 제한된 자유 공간 생성
        free_spaces = [FreeSpace(region_x, region_y, region_w, region_h)]
        placed = []

        # 그룹들을 면적순으로 정렬 (큰 그룹 우선)
        groups_sorted = sorted(groups, key=lambda g: g['total_area'], reverse=True)

        total_pieces = sum(g['count'] for g in groups_sorted)
        piece_counter = 0

        for group in groups_sorted:
            # 그룹 내 모든 조각 배치
            preferred_rotated = group['rotated']

            print(f"  [그룹 배치] {group['size'][0]}×{group['size'][1]}, {group['count']}개, 회전: {preferred_rotated}")

            # 그룹 내 조각들을 같은 크기이므로 격자 형태로 배치 시도
            group_pieces = group['pieces']

            # 조각 크기 계산 (회전 고려)
            if preferred_rotated:
                piece_w, piece_h = group['size'][1], group['size'][0]
            else:
                piece_w, piece_h = group['size'][0], group['size'][1]

            # 영역 내에서 배치 가능한 행/열 계산
            cols_per_row = (region_w + self.kerf) // (piece_w + self.kerf)
            rows_available = (region_h + self.kerf) // (piece_h + self.kerf)

            print(f"    영역 크기: {region_w}×{region_h}mm")
            print(f"    조각 크기 (회전 적용): {piece_w}×{piece_h}mm")
            print(f"    가능한 배치: {cols_per_row}열 × {rows_available}행 = 최대 {cols_per_row * rows_available}개")

            if cols_per_row == 0 or rows_available == 0:
                print("    ⚠️  조각이 너무 커서 영역에 배치 불가!")
                return None

            # 그룹 조각들을 격자로 배치
            pieces_placed_count = 0

            for piece in group_pieces:
                piece_counter += 1

                # AlignedFreeSpace 방식으로 배치 시도
                placement = self._find_placement_aligned(
                    free_spaces, placed, piece, preferred_rotated, region_x, region_y, region_w, region_h
                )

                if placement:
                    # FreeSpace 업데이트 (L자형 분할)
                    self._apply_placement(free_spaces, placed, piece, placement)
                    pieces_placed_count += 1
                    print(f"    조각 {piece_counter}/{total_pieces}: {piece['width']}×{piece['height']} → ({placement['x']}, {placement['y']}) {placement['width']}×{placement['height']}")
                else:
                    # 배치 실패
                    print(f"    조각 {piece_counter}/{total_pieces}: {piece['width']}×{piece['height']} → 배치 실패!")
                    print(f"      남은 FreeSpace: {len(free_spaces)}개")
                    for i, fs in enumerate(free_spaces[:5]):
                        print(f"        [{i+1}] ({fs.x}, {fs.y}) {fs.width}×{fs.height}mm")

                    # 그룹 깨기: 배치된 조각만으로 계속 진행
                    print(f"    ⚠️  그룹 일부만 배치 ({pieces_placed_count}/{len(group_pieces)}개), 나머지는 다른 영역에 할당 필요")
                    # 실패해도 None 반환하지 않고 계속 진행 (다음 그룹 시도)
                    break

            print(f"  [그룹 완료] {pieces_placed_count}/{len(group_pieces)}개 배치 성공")

        print(f"  [영역 완료] 총 {len(placed)}/{total_pieces}개 배치")

        # 일부라도 배치 성공하면 반환
        return placed if placed else None

    def _recalculate_free_spaces(self, placed_pieces, plate_w, plate_h):
        """배치된 조각들로부터 FreeSpace 재계산 (단순화 버전)

        Args:
            placed_pieces: 이미 배치된 조각 리스트
            plate_w: 판 너비
            plate_h: 판 높이

        Returns:
            FreeSpace 리스트
        """
        # 간단한 구현: 전체 판을 초기 FreeSpace로 시작
        # 각 배치된 조각에 대해 FreeSpace를 분할
        free_spaces = [FreeSpace(0, 0, plate_w, plate_h)]

        for piece in placed_pieces:
            x, y = piece['x'], piece['y']
            w = piece.get('placed_w', piece['height'] if piece.get('rotated') else piece['width'])
            h = piece.get('placed_h', piece['width'] if piece.get('rotated') else piece['height'])

            # 기존 FreeSpace들과 겹치는 부분 처리
            new_free_spaces = []
            for space in free_spaces:
                # 조각과 겹치지 않으면 유지
                if (x >= space.x + space.width or x + w + self.kerf <= space.x or
                    y >= space.y + space.height or y + h + self.kerf <= space.y):
                    new_free_spaces.append(space)
                else:
                    # 겹치는 경우 분할 (간단한 L자형 분할)
                    # 우측 공간
                    if space.x + space.width > x + w + self.kerf:
                        new_free_spaces.append(FreeSpace(
                            x + w + self.kerf, space.y,
                            space.x + space.width - (x + w + self.kerf), space.height
                        ))
                    # 상단 공간
                    if space.y + space.height > y + h + self.kerf:
                        new_free_spaces.append(FreeSpace(
                            space.x, y + h + self.kerf,
                            space.width, space.y + space.height - (y + h + self.kerf)
                        ))

            free_spaces = new_free_spaces

        return free_spaces

    def _find_best_placement_simple(self, free_spaces, placed, piece):
        """단순한 AlignedFreeSpace 배치 (전체 판 대상)

        Args:
            free_spaces: 사용 가능한 FreeSpace 리스트
            placed: 이미 배치된 조각 리스트
            piece: 배치할 조각

        Returns:
            placement dict 또는 None
        """
        w, h = piece['width'], piece['height']

        candidates = []

        for space in free_spaces:
            # 비회전
            if w + self.kerf <= space.width and h + self.kerf <= space.height:
                waste = (space.width - w) * (space.height - h)
                candidates.append({
                    'space': space, 'x': space.x, 'y': space.y,
                    'width': w, 'height': h, 'rotated': False,
                    'waste': waste
                })

            # 회전
            if self.allow_rotation and h + self.kerf <= space.width and w + self.kerf <= space.height:
                waste = (space.width - h) * (space.height - w)
                candidates.append({
                    'space': space, 'x': space.x, 'y': space.y,
                    'width': h, 'height': w, 'rotated': True,
                    'waste': waste
                })

        if not candidates:
            return None

        # 낭비가 적은 순으로 정렬
        candidates.sort(key=lambda c: c['waste'])
        return candidates[0]

    def _find_placement_aligned(self, free_spaces, placed, piece, preferred_rotated, rx, ry, rw, rh):
        """AlignedFreeSpace 방식의 배치 후보 찾기

        Args:
            preferred_rotated: 클러스터링에서 결정된 선호 회전 상태

        Returns:
            placement dict 또는 None
        """
        w, h = piece['width'], piece['height']

        # 영역 경계 및 기존 조각 좌표 수집
        existing_x = {rx}
        existing_y = {ry}

        for p in placed:
            if rx <= p['x'] < rx + rw:
                existing_x.add(p['x'])
                pw = p.get('placed_w', p['height'] if p.get('rotated') else p['width'])
                ph = p.get('placed_h', p['width'] if p.get('rotated') else p['height'])
                existing_x.add(p['x'] + pw + self.kerf)
                existing_y.add(p['y'])
                existing_y.add(p['y'] + ph + self.kerf)

        candidates = []

        for space in free_spaces:
            # 영역 내 공간만 고려
            if not (rx <= space.x < rx + rw and ry <= space.y < ry + rh):
                continue

            # 선호 회전 상태 우선 시도
            if preferred_rotated:
                test_w, test_h = h, w
            else:
                test_w, test_h = w, h

            # 후보 생성 (선호 방향)
            if test_w + self.kerf <= space.width and test_h + self.kerf <= space.height:
                alignment_score = (1 if space.x in existing_x else 0) + (1 if space.y in existing_y else 0)
                waste = (space.width - test_w) * (space.height - test_h)
                rotation_bonus = 100 if (preferred_rotated == (test_w == h)) else 0

                candidates.append({
                    'space': space, 'x': space.x, 'y': space.y,
                    'width': test_w, 'height': test_h,
                    'rotated': (test_w == h),  # w가 h와 같으면 회전됨
                    'alignment_score': alignment_score,
                    'waste': waste,
                    'rotation_bonus': rotation_bonus
                })

            # 다른 회전 상태도 시도 (allow_rotation이면)
            if self.allow_rotation:
                alt_w, alt_h = test_h, test_w
                if alt_w + self.kerf <= space.width and alt_h + self.kerf <= space.height:
                    alignment_score = (1 if space.x in existing_x else 0) + (1 if space.y in existing_y else 0)
                    waste = (space.width - alt_w) * (space.height - alt_h)
                    rotation_bonus = 0  # 비선호 회전

                    candidates.append({
                        'space': space, 'x': space.x, 'y': space.y,
                        'width': alt_w, 'height': alt_h,
                        'rotated': (alt_w == h),
                        'alignment_score': alignment_score,
                        'waste': waste,
                        'rotation_bonus': rotation_bonus
                    })

        if not candidates:
            return None

        # 정렬: rotation_bonus > alignment_score > waste
        candidates.sort(key=lambda c: (-c['rotation_bonus'], -c['alignment_score'], c['waste']))
        return candidates[0]

    def _apply_placement(self, free_spaces, placed, piece, placement):
        """배치 적용 및 FreeSpace 업데이트"""
        space = placement['space']
        x, y = placement['x'], placement['y']
        w, h = placement['width'], placement['height']

        placed.append({
            **piece, 'x': x, 'y': y,
            'rotated': placement['rotated']
        })

        free_spaces.remove(space)

        # L자형 분할 (우측 공간 + 상단 공간)
        if space.width > w + self.kerf:
            free_spaces.append(FreeSpace(
                x + w + self.kerf, y,
                space.width - w - self.kerf, h + self.kerf
            ))

        if space.height > h + self.kerf:
            free_spaces.append(FreeSpace(
                x, y + h + self.kerf,
                space.width, space.height - h - self.kerf
            ))

