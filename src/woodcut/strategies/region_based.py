"""영역 기반 패킹 전략 - 높이/너비 혼합 그룹화

사용자 수동 배치 패턴을 구현한 알고리즘:
- 각 조각의 회전/비회전 옵션 모두 고려
- 높이 기반 + 너비 기반 클러스터링
- 수평 절단 + 수직 절단 영역 혼합
- 작업 편의성: 같은 높이/너비 조각들이 그룹화
"""

from __future__ import annotations
from ..packing import PackingStrategy, FreeSpace


class RegionBasedPacker(PackingStrategy):
    """전략 6: 높이/너비 혼합 그룹화 패킹

    핵심 아이디어:
    - 각 조각의 회전/비회전 옵션 모두 고려
    - 높이 기반 + 너비 기반 클러스터링
    - 수평 절단 + 수직 절단 영역 혼합
    - 작업 편의성: 같은 높이/너비 조각들이 그룹화
    """

    def __init__(self, plate_width: int, plate_height: int, kerf: int = 5, allow_rotation: bool = True) -> None:
        super().__init__(plate_width, plate_height, kerf, allow_rotation)

    def pack(self, pieces: list[tuple[int, int, int]]) -> list[dict]:
        """다중 그룹 영역 배치 패킹 (재설계)"""
        all_pieces = self.expand_pieces(pieces)
        plates = []
        remaining_pieces = all_pieces[:]

        plate_num = 1

        while remaining_pieces:
            print(f"\n=== 원판 {plate_num}: 다중 그룹 영역 배치 시작 ===")
            print(f"남은 조각: {len(remaining_pieces)}개")

            # 1. 레벨 1: 정확히 같은 크기끼리 그룹화
            groups = self._group_by_exact_size(remaining_pieces)

            print(f"\n레벨 1: {len(groups)}개 그룹 생성")
            for i, group in enumerate(groups):
                print(f"  그룹 {i+1}: {group['size'][0]}×{group['size'][1]}mm, {group['count']}개 조각, 총 면적 {group['total_area']:,}mm²")

            # 2. 각 그룹의 회전 옵션 생성
            group_options = self._generate_group_options(groups)

            # 3. 회전 옵션 평면화
            all_variants = self._flatten_group_options(group_options)

            # 4. 앵커 기반 백트래킹으로 최적 조합 찾기
            regions = self._allocate_anchor_backtrack(all_variants)

            if not regions:
                print("\n⚠️  백트래킹 실패, AlignedFreeSpace 폴백")
                plate = {'pieces': [], 'cuts': [], 'free_spaces': [FreeSpace(0, 0, self.plate_width, self.plate_height)]}
                for piece in remaining_pieces:
                    placement = self._find_best_placement_simple(plate['free_spaces'], plate['pieces'], piece)
                    if placement:
                        self._apply_placement(plate['free_spaces'], plate['pieces'], piece, placement)
                self.generate_guillotine_cuts(plate)
                plates.append(plate)
                break

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
                    is_last_region=(i == len(regions) - 1)
                )
                if placed:
                    plate['pieces'].extend(placed)

                # 절단선은 조각 유무와 관계없이 추가 (자투리 영역 포함)
                if cuts:
                    for cut in cuts:
                        cut['region_index'] = i
                    all_cuts.extend(cuts)

            # 절단선 우선순위 + 영역 순서 정렬
            # Priority 1 (영역 경계): position 순 (위→아래)
            # Priority 2-6 (영역 내부): region_index 순 → sub_priority 순 → position 순
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

            print(f"\n=== 원판 {plate_num}: 다중 그룹 영역 배치 완료 ===")
            print(f"  배치된 조각: {len(plate['pieces'])}개")
            print(f"  절단선: {len(plate['cuts'])}개\n")

            plates.append(plate)

            # 7. 배치된 조각들을 remaining_pieces에서 제거
            placed_sizes = {}
            for p in plate['pieces']:
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

            # 무한 루프 방지
            if plate_num > 10:
                print("\n⚠️  최대 원판 수 초과 (10장)")
                break

        return plates

    
    

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
                total_width = w * count + (count - 1) * self.kerf

                variants.append({
                    'original_size': original_size,
                    'count': count,
                    'rotated': option['rotated'],
                    'height': h,
                    'width': w,
                    'total_width': total_width,
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
            'count': anchor['count']
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
                    'count': v['count']
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
                    'groups': region_groups
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
                    'groups': []
                }
                regions.append(scrap_region)
                print(f"[자투리 영역 추가] y={scrap_region['y']}, height={remaining_height}mm")

        print(f"[앵커 백트래킹 완료] {count}개 조각 배치, {len(regions)}개 영역")

        return regions

    def _pack_multi_group_region(self, region, region_id, region_index, is_first_region, is_last_region=False):
        """한 영역에 여러 그룹 배치 + 절단선 생성

        Args:
            region: _allocate_anchor_backtrack()가 생성한 영역 정보
            region_id: 영역 ID (예: 'R1', 'R2')
            region_index: 영역 인덱스 (0부터 시작)
            is_first_region: 첫 번째 영역 여부
            is_last_region: 마지막 영역 여부

        Returns:
            (placed_pieces, cuts)  # 조각 리스트, 절단선 리스트
        """
        placed = []
        cuts = []
        current_x = region['x']
        region_y = region['y']
        max_height = region['max_height']

        print(f"\n[영역 배치] {region['type']}, y={region_y}, max_height={max_height}")

        # 자투리 영역은 경계 절단선만 생성하고 종료
        if region['type'] == 'scrap':
            if not is_first_region:
                cuts.append({
                    'direction': 'H',
                    'position': region_y,
                    'start': 0,
                    'end': self.plate_width,
                    'priority': 1,
                    'type': 'scrap_boundary'
                })
            return placed, cuts

        # 영역 경계 절단선 (첫 영역 제외)
        # 우선순위 1: 영역 경계 (길로틴 순서 최우선)
        if not is_first_region:
            cuts.append({
                'direction': 'H',
                'position': region_y,
                'start': 0,
                'end': self.plate_width,
                'priority': 1,
                'type': 'region_boundary'
            })

        for group in region['groups']:
            w, h = group['original_size']
            rotated = group['rotated']
            count = group['count']

            # 회전 적용
            piece_w = h if rotated else w
            piece_h = w if rotated else h

            # 상단 정렬 (절단 로직과 일치)
            y_offset = 0
            
            print(f"  그룹 {w}×{h} (회전={rotated}): {count}개 → y_offset={y_offset}")

            # 그룹의 모든 조각 배치 (수평 방향)
            for _ in range(count):
                # 공간 체크
                if current_x + piece_w > region['x'] + region['width']:
                    print(f"    ⚠️  공간 부족: current_x={current_x}, piece_w={piece_w}, region_width={region['width']}")
                    return None, []  # 배치 실패

                placed.append({
                    'width': w,
                    'height': h,
                    'x': current_x,
                    'y': region_y + y_offset,
                    'rotated': rotated,
                    # placed_w/h는 절단 알고리즘이 설정 (미리 설정하면 트리밍 절단 생성 안 됨)
                    'id': len(placed),
                    'original': (w, h)
                })

                current_x += piece_w + self.kerf

        print(f"  → {len(placed)}개 조각 배치 성공")

        # 절단선 생성
        if not placed:
            return placed, cuts

        # 1. x 위치로 정렬
        sorted_pieces = sorted(placed, key=lambda p: p['x'])

        # 2. 높이별로 그룹 분할
        groups = []  # [{pieces: [...], height: h}, ...]
        curr_group = {'pieces': [sorted_pieces[0]], 'height': None}
        
        for i, piece in enumerate(sorted_pieces):
            piece_h = piece['width'] if piece.get('rotated') else piece['height']
            
            if curr_group['height'] is None:
                curr_group['height'] = piece_h
            
            if i > 0:
                prev_h = sorted_pieces[i-1]['width'] if sorted_pieces[i-1].get('rotated') else sorted_pieces[i-1]['height']
                if abs(piece_h - prev_h) > 1:  # 높이가 다르면 새 그룹
                    groups.append(curr_group)
                    curr_group = {'pieces': [piece], 'height': piece_h}
                else:
                    curr_group['pieces'].append(piece)
        
        groups.append(curr_group)  # 마지막 그룹 추가
        
        max_height_in_region = max(g['height'] for g in groups)
        
        # 3. 영역 상단 자투리 trim (Priority 2)
        if abs(max_height_in_region - max_height) > 1:
            cuts.append({
                'direction': 'H',
                'position': region_y + max_height_in_region,
                'start': region['x'],
                'end': region['x'] + region['width'],
                'priority': 2,
                'type': 'region_trim'
            })
            print(f"  → 영역 상단 trim: y={region_y + max_height_in_region}")
        
        # 4. 그룹별 인터리브 절단선 생성
        for group_idx, group in enumerate(groups):
            group_pieces = group['pieces']
            group_h = group['height']
            
            # Priority base = 5 + group_idx * 10
            priority_base = 5 + group_idx * 10
            
            # 4a. 현재 그룹 내 조각 분리 (piece_separation)
            for i in range(len(group_pieces) - 1):
                curr = group_pieces[i]
                curr_w = curr['height'] if curr.get('rotated') else curr['width']
                
                cuts.append({
                    'direction': 'V',
                    'position': curr['x'] + curr_w,
                    'start': region_y,
                    'end': region_y + group_h,
                    'priority': priority_base,
                    'type': 'piece_separation',
                    'sub_priority': 1
                })
            
            # 4b. 그룹 우측 자투리 trim (마지막 조각 후)
            last_piece = group_pieces[-1]
            last_w = last_piece['height'] if last_piece.get('rotated') else last_piece['width']
            last_x_end = last_piece['x'] + last_w
            
            # 마지막 그룹이면 영역 끝까지, 아니면 다음 그룹 시작까지
            if group_idx == len(groups) - 1:
                region_x_end = region['x'] + region['width']
                if region_x_end - last_x_end > self.kerf:
                    cuts.append({
                        'direction': 'V',
                        'position': last_x_end,
                        'start': region_y,
                        'end': region_y + group_h,
                        'priority': priority_base,
                        'type': 'right_trim',
                        'sub_priority': 2
                    })
            
            # 4c. 다음 그룹과의 경계 (group_boundary)
            if group_idx < len(groups) - 1:
                next_group = groups[group_idx + 1]
                next_h = next_group['height']
                
                # 경계 위치: 현재 그룹 마지막 조각 끝
                boundary_x = last_x_end
                
                cuts.append({
                    'direction': 'V',
                    'position': boundary_x,
                    'start': region_y,
                    'end': region_y + max(group_h, next_h),  # 두 그룹 중 더 높은 곳까지
                    'priority': priority_base + 1,
                    'type': 'group_boundary',
                    'sub_priority': 0
                })
                print(f"  → 그룹 경계: x={boundary_x} (그룹 {group_idx} vs {group_idx+1})")
                
                # 4d. 다음 그룹 높이 trim (필요한 경우만)
                if next_h < group_h:
                    cuts.append({
                        'direction': 'H',
                        'position': region_y + next_h,
                        'start': boundary_x,
                        'end': region['x'] + region['width'],  # 영역 끝까지
                        'priority': priority_base + 2,
                        'type': 'group_trim',
                        'sub_priority': 0
                    })
                    print(f"  → 다음 그룹 trim: y={region_y + next_h}, x={boundary_x}~끝")
        
        # 5. placed_w/h 설정
        for piece in placed:
            if piece.get('rotated', False):
                piece['placed_w'] = piece['height']
                piece['placed_h'] = piece['width']
            else:
                piece['placed_w'] = piece['width']
                piece['placed_h'] = piece['height']

        return placed, cuts

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

