"""영역 기반 패킹 전략 + 그룹 자동 분할

RegionBasedPacker의 Fallback 전략:
- 배치 실패 시 큰 그룹을 자동 분할하여 재시도
- 무한 루프 방지: 분할 후에도 실패하면 즉시 중단
"""

from __future__ import annotations
from .region_based import RegionBasedPacker


class RegionBasedPackerWithSplit(RegionBasedPacker):
    """그룹 자동 분할을 지원하는 영역 기반 패커

    RegionBasedPacker를 상속하여 다음 기능 추가:
    - 실패 후 분할: 회전 옵션 먼저 시도, 실패 시에만 그룹 분할
    - 무한 루프 방지: 분할 후에도 배치 실패 시 즉시 중단
    """

    def __init__(self, plate_width: int, plate_height: int, kerf: int = 5, allow_rotation: bool = True,
                 enable_multi_tier: bool = False, multi_tier_threshold: int = 100) -> None:
        super().__init__(plate_width, plate_height, kerf, allow_rotation, enable_multi_tier, multi_tier_threshold)

    def pack(self, pieces: list[tuple[int, int, int]]) -> list[dict]:
        """다중 그룹 영역 배치 패킹 (그룹 분할 지원)"""
        all_pieces = self.expand_pieces(pieces)
        plates = []
        remaining_pieces = all_pieces[:]

        plate_num = 1

        while remaining_pieces:
            print(f"\n=== 원판 {plate_num}: 다중 그룹 영역 배치 시작 (분할 지원) ===")
            print(f"남은 조각: {len(remaining_pieces)}개")

            # 1. 레벨 1: 정확히 같은 크기끼리 그룹화
            groups = self._group_by_exact_size(remaining_pieces)

            print(f"\n레벨 1: {len(groups)}개 그룹 생성")
            for i, group in enumerate(groups):
                print(f"  그룹 {i+1}: {group['size'][0]}×{group['size'][1]}mm, {group['count']}개 조각, 총 면적 {group['total_area']:,}mm²")

            # ★ 2. 1차 시도: 분할 없이 백트래킹 (회전 옵션 포함)
            plate, regions = self._try_pack_groups(groups, plate_num)

            # ★ 3. 배치 실패 시 그룹 분할 후 재시도
            if len(plate['pieces']) == 0:
                print("\n⚠️  배치 실패, 큰 그룹 분할 후 재시도...")

                # 그룹 분할
                groups = self._split_oversized_groups(groups)

                print(f"분할 후 그룹 수: {len(groups)}개")

                # 재시도
                plate, regions = self._try_pack_groups(groups, plate_num)

                # ★ 분할 후에도 실패 → 중단
                if len(plate['pieces']) == 0:
                    print("\n❌ 오류: 원판에 조각을 배치할 수 없습니다")
                    print(f"남은 조각: {len(remaining_pieces)}개")
                    for idx, piece in enumerate(remaining_pieces[:3]):  # 최대 3개만 표시
                        print(f"  {idx+1}. {piece['width']}×{piece['height']}mm")
                    if len(remaining_pieces) > 3:
                        print(f"  ... 외 {len(remaining_pieces) - 3}개")
                    break

            # ★ Multi-Tier 옵션이 켜진 경우 (배치 성공 후)
            if self.enable_multi_tier and remaining_pieces and len(plate['pieces']) > 0 and regions:
                # 다단 배치 전에 현재 plate의 조각들을 제거 (임시)
                placed_in_plate = {}
                for p in plate['pieces']:
                    size_key = (p['width'], p['height'])
                    placed_in_plate[size_key] = placed_in_plate.get(size_key, 0) + 1

                filtered_remaining = []
                for piece in remaining_pieces:
                    size_key = (piece['width'], piece['height'])
                    if size_key in placed_in_plate and placed_in_plate[size_key] > 0:
                        placed_in_plate[size_key] -= 1
                    else:
                        filtered_remaining.append(piece)

                print("\n=== 다단 배치 시도 ===")
                print(f"현재 plate 제외 후 남은 조각: {len(filtered_remaining)}개")

                for region in regions:
                    # scrap 영역 제외
                    if region['type'] == 'scrap':
                        continue

                    # 남은 공간 탐지
                    space = self._detect_remaining_space(region)

                    if space:
                        width, height, y_offset = space
                        existing_h = region['rows'][0]['height']

                        print(f"영역 {region.get('id', '?')}: 남은 {height}mm 탐지")

                        # 추가 행 시도 (현재 plate 제외한 조각들로)
                        extra_row = self._try_add_tier(
                            filtered_remaining,
                            width,
                            height
                        )

                        if extra_row:
                            # 추가 행 배치
                            region['rows'].append(extra_row)
                            region['height'] += extra_row['height']

                            # 추가 행 정보 로깅
                            placed_count = sum(g['count'] for g in extra_row['groups'])
                            print(f"  → 추가 행 추가: {placed_count}개 조각 (제거는 나중에)")

                            # 영역 전체를 다시 배치 (추가 행 포함)
                            region_idx = regions.index(region)
                            placed_new, cuts_new = self._pack_multi_group_region(
                                region,
                                region.get('id', f'R{region_idx+1}'),
                                region_index=region_idx,
                                is_first_region=(region_idx == 0),
                                is_last_region=(region_idx == len(regions) - 1),
                                region_priority_base=region_idx * 100
                            )
                            
                            if placed_new:
                                # 기존 plate의 이 영역 조각들을 교체
                                # (간단하게: plate를 다시 생성)
                                plate = {'pieces': [], 'cuts': [], 'free_spaces': []}
                                all_cuts = []
                                
                                for i, r in enumerate(regions):
                                    r['id'] = f'R{i+1}'
                                    placed_r, cuts_r = self._pack_multi_group_region(
                                        r,
                                        r['id'],
                                        region_index=i,
                                        is_first_region=(i == 0),
                                        is_last_region=(i == len(regions) - 1),
                                        region_priority_base=i * 100
                                    )
                                    if placed_r:
                                        plate['pieces'].extend(placed_r)
                                    if cuts_r:
                                        for cut in cuts_r:
                                            cut['region_index'] = i
                                        all_cuts.extend(cuts_r)
                                
                                # 절단선 정렬
                                def sort_key(cut):
                                    priority = cut.get('priority', 100)
                                    region_idx = cut.get('region_index', 0)
                                    sub_priority = cut.get('sub_priority', 0)
                                    position = cut.get('position', 0)
                                    if priority == 1:
                                        return (priority, position, 0, 0)
                                    else:
                                        return (priority, region_idx, sub_priority, position)
                                
                                all_cuts.sort(key=sort_key)
                                for idx, cut in enumerate(all_cuts):
                                    cut['order'] = idx + 1
                                    if 'region_x' not in cut:
                                        cut['region_x'] = 0
                                        cut['region_y'] = 0
                                        cut['region_w'] = self.plate_width
                                        cut['region_h'] = self.plate_height
                                plate['cuts'] = all_cuts
                                
                                break  # 한 영역에만 추가 행 배치
                        else:
                            print(f"  → 조건 불충족, 스킵")

            print(f"\n=== 원판 {plate_num}: 다중 그룹 영역 배치 완료 ===")
            print(f"  배치된 조각: {len(plate['pieces'])}개")
            print(f"  절단선: {len(plate['cuts'])}개\n")

            plates.append(plate)

            # ★ 검증: 배치된 조각 수 확인
            placed_sizes_count = {}
            for p in plate['pieces']:
                size_key = (p['width'], p['height'])
                placed_sizes_count[size_key] = placed_sizes_count.get(size_key, 0) + 1

            print(f"\n=== 배치 검증 ===")
            for size_key, count in placed_sizes_count.items():
                print(f"  {size_key[0]}×{size_key[1]}: {count}개 배치")

            # 4. 배치된 조각들을 remaining_pieces에서 제거
            placed_sizes = placed_sizes_count  # 이미 계산한 값 재사용

            new_remaining = []
            for piece in remaining_pieces:
                size_key = (piece['width'], piece['height'])
                if size_key in placed_sizes and placed_sizes[size_key] > 0:
                    placed_sizes[size_key] -= 1
                else:
                    new_remaining.append(piece)

            remaining_pieces = new_remaining
            plate_num += 1

            # 무한 루프 방지
            if plate_num > 10:
                print("\n⚠️  최대 원판 수 초과 (10장)")
                break

        return plates

    def _try_pack_groups(self, groups: list[dict], plate_num: int) -> tuple[dict, list]:
        """그룹 배치 시도

        Args:
            groups: 그룹 리스트
            plate_num: 원판 번호 (로깅용)

        Returns:
            (plate, regions) 튜플
            - plate: 딕셔너리 {'pieces': [...], 'cuts': [...]}
            - regions: 영역 리스트
        """
        # 2. 각 그룹의 회전 옵션 생성
        group_options = self._generate_group_options(groups)

        # 3. 회전 옵션 평면화
        all_variants = self._flatten_group_options(group_options)

        # 4. 앵커 기반 백트래킹으로 최적 조합 찾기
        regions = self._allocate_anchor_backtrack(all_variants)

        if not regions:
            print("\n⚠️  백트래킹 실패")
            return {'pieces': [], 'cuts': [], 'free_spaces': []}, []

        # 5. 각 영역 내 배치 및 절단선 생성
        plate = {'pieces': [], 'cuts': [], 'free_spaces': []}

        # 영역 ID 할당
        for i, region in enumerate(regions):
            region['id'] = f'R{i+1}'

        # 각 영역 배치 + 절단선 생성
        all_cuts = []
        for i, region in enumerate(regions):
            placed, cuts = self._pack_multi_group_region(
                region,
                region['id'],
                region_index=i,
                is_first_region=(i == 0),
                is_last_region=(i == len(regions) - 1),
                region_priority_base=i * 100
            )
            if placed:
                plate['pieces'].extend(placed)

            # 절단선은 조각 유무와 관계없이 추가 (자투리 영역 포함)
            if cuts:
                for cut in cuts:
                    cut['region_index'] = i
                all_cuts.extend(cuts)

        # 절단선 우선순위 + 영역 순서 정렬
        def sort_key(cut):
            priority = cut.get('priority', 100)
            region_idx = cut.get('region_index', 0)
            sub_priority = cut.get('sub_priority', 0)
            position = cut.get('position', 0)

            if priority == 1:  # 영역 경계: position만 고려
                return (priority, position, 0, 0)
            else:  # 영역 내부: region_index → sub_priority → position
                return (priority, region_idx, sub_priority, position)

        all_cuts.sort(key=sort_key)
        for idx, cut in enumerate(all_cuts):
            cut['order'] = idx + 1
            # region 정보 추가 (시각화용)
            if 'region_x' not in cut:
                cut['region_x'] = 0
                cut['region_y'] = 0
                cut['region_w'] = self.plate_width
                cut['region_h'] = self.plate_height
        plate['cuts'] = all_cuts

        return plate, regions

    def _split_oversized_groups(self, groups: list[dict]) -> list[dict]:
        """한 행에 들어가지 않는 그룹을 자동 분할 (회전 및 세로 쌓기 고려)

        Args:
            groups: 그룹 리스트

        Returns:
            분할된 그룹 리스트
        """
        result = []

        for group in groups:
            w, h = group['size']
            count = group['count']
            pieces = group['pieces']

            # RegionBasedPacker는 수평 배치만 지원하므로,
            # 실제로 백트래킹이 배치할 수 있는 옵션만 고려

            # 1. 수평 배치 (비회전): w×h 그대로
            #    - 한 행에: (plate_width) // (w + kerf) 개
            #    - 높이 확인: h <= plate_height
            max_horizontal = (self.plate_width + self.kerf) // (w + self.kerf) if h <= self.plate_height else 0

            # 2. 수평 배치 (회전): h×w로 회전, 회전 허용 시
            #    - 한 행에: (plate_width) // (h + kerf) 개
            #    - 높이 확인: w <= plate_height (회전 후 높이가 w)
            max_rotated = (self.plate_width + self.kerf) // (h + self.kerf) if self.allow_rotation and w <= self.plate_height else 0

            # 최대값 선택 (회전 vs 비회전 중 더 많이 들어가는 쪽)
            if max_rotated > max_horizontal:
                max_count = max_rotated
                best_option = 'rotated'
            else:
                max_count = max_horizontal
                best_option = 'horizontal'

            if max_count == 0:
                # 조각이 원판보다 큼 → 경고 후 그대로 추가 (배치 실패할 것)
                print(f"  ⚠️  {w}×{h}mm 조각이 원판보다 큽니다")
                result.append(group)
                continue

            if count <= max_count:
                # 분할 불필요
                result.append(group)
            else:
                # 분할 필요
                option_desc = f"회전 {max_count}개" if best_option == 'rotated' else f"{max_count}개"
                print(f"  분할: {w}×{h}mm {count}개 → {option_desc}씩 그룹")

                remaining_count = count
                piece_idx = 0

                while remaining_count > 0:
                    split_count = min(max_count, remaining_count)

                    result.append({
                        'size': (w, h),
                        'count': split_count,
                        'pieces': pieces[piece_idx:piece_idx + split_count],
                        'total_area': w * h * split_count
                    })

                    remaining_count -= split_count
                    piece_idx += split_count

        return result
