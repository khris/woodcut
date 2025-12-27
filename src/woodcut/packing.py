"""
기본 클래스 모듈
- Region: 절단으로 생긴 영역
- FreeSpace: 자유 공간 사각형
- PackingStrategy: 패킹 전략 베이스 클래스 (Guillotine Cut 알고리즘 포함)
"""

from __future__ import annotations
from abc import ABC, abstractmethod


class Region:
    """절단으로 생긴 영역"""
    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.pieces = []
        self.children = []
        self.cut = None


class FreeSpace:
    """자유 공간 사각형"""
    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y
        self.width = width
        self.height = height


class PackingStrategy(ABC):
    """패킹 전략 베이스 클래스"""

    def __init__(self, plate_width: int, plate_height: int, kerf: int = 5, allow_rotation: bool = True) -> None:
        self.plate_width: int = plate_width
        self.plate_height: int = plate_height
        self.kerf: int = kerf
        self.allow_rotation: bool = allow_rotation

    @abstractmethod
    def pack(self, pieces: list[tuple[int, int, int]]) -> list[dict]:
        """조각들을 판에 배치

        Args:
            pieces: [(width, height, count), ...] 형식의 조각 목록

        Returns:
            판별 배치 결과 리스트, 각 판은 {'pieces': [...], 'cuts': [...]} 구조
        """
        pass

    def expand_pieces(self, pieces: list[tuple[int, int, int]]) -> list[dict]:
        """조각을 개별 아이템으로 확장"""
        all_pieces: list[dict] = []
        piece_id = 0
        for width, height, count in pieces:
            for i in range(count):
                all_pieces.append({
                    'width': width,
                    'height': height,
                    'area': width * height,
                    'id': piece_id,
                    'original': (width, height)
                })
                piece_id += 1
        return all_pieces

    def generate_guillotine_cuts(self, plate):
        """실제 Guillotine Cut 시퀀스 생성"""
        if not plate['pieces']:
            return

        plate['cuts'] = []
        cut_order = [1]

        root_region = Region(0, 0, self.plate_width, self.plate_height)
        root_region.pieces = plate['pieces']

        self._split_region(root_region, plate['cuts'], cut_order)

        # 후처리: 모든 조각의 placed_w/h 최종 설정
        for piece in plate['pieces']:
            if 'placed_w' not in piece:
                piece['placed_w'] = piece['height'] if piece.get('rotated') else piece['width']
            if 'placed_h' not in piece:
                piece['placed_h'] = piece['width'] if piece.get('rotated') else piece['height']

    def _all_pieces_exact(self, region):
        """영역 내 모든 조각이 정확한 크기인지 확인"""
        for piece in region.pieces:
            # placed_w, placed_h가 없으면 아직 트리밍되지 않음
            if 'placed_w' not in piece or 'placed_h' not in piece:
                return False

            actual_w = piece['placed_w']
            actual_h = piece['placed_h']

            # 회전 여부에 따라 필요한 크기 결정
            if piece.get('rotated', False):
                # 회전된 경우: placed_w는 원래의 height, placed_h는 원래의 width
                required_w = piece['height']
                required_h = piece['width']
            else:
                required_w = piece['width']
                required_h = piece['height']

            # 1mm 오차 허용
            if abs(actual_w - required_w) > 1 or abs(actual_h - required_h) > 1:
                return False
        return True

    def _generate_trimming_cuts(self, region):
        """조각들을 정확한 크기로 트리밍하는 절단선 생성"""
        trimming_cuts = []

        # 모든 조각의 경계선 수집 (필요한 크기 기준)
        y_boundaries = set()
        x_boundaries = set()

        for piece in region.pieces:
            # 회전 고려: 필요한 크기 계산
            req_w = piece['height'] if piece.get('rotated', False) else piece['width']
            req_h = piece['width'] if piece.get('rotated', False) else piece['height']

            # 조각의 필요한 끝 위치
            y_boundaries.add((piece['y'] + req_h, req_h))
            x_boundaries.add((piece['x'] + req_w, req_w))

        # 수평 절단선: 같은 y 시작점의 조각들을 높이별로 sub-group화하여 트리밍
        # 먼저 y 시작점별로 그룹화
        y_groups = {}
        for piece in region.pieces:
            y_start = piece['y']
            if y_start not in y_groups:
                y_groups[y_start] = []
            y_groups[y_start].append(piece)

        # 각 y 그룹을 높이별로 sub-group화
        for y_start, pieces_at_y in y_groups.items():
            # 높이별로 sub-group 생성
            height_subgroups = {}
            for p in pieces_at_y:
                p_req_h = p['width'] if p.get('rotated', False) else p['height']
                if p_req_h not in height_subgroups:
                    height_subgroups[p_req_h] = []
                height_subgroups[p_req_h].append(p)

            # 각 높이별 sub-group에 대해 독립적으로 절단선 생성
            for req_h, pieces_with_height in height_subgroups.items():
                cut_y = y_start + req_h

                if region.y < cut_y < region.y + region.height:
                    # 이 절단으로 영향받는 조각들 (같은 높이를 가진 조각들만)
                    affected_pieces = pieces_with_height

                    # 아래쪽에 다른 조각이 있는지 확인
                    pieces_below = []
                    for p in region.pieces:
                        if p not in pieces_with_height:  # 다른 높이 또는 다른 y
                            p_req_h = p['width'] if p.get('rotated', False) else p['height']
                            actual_h = p.get('placed_h', p_req_h)
                            if p['y'] + actual_h <= cut_y:
                                pieces_below.append(p)

                    # 절단이 필요한 경우:
                    # 1) 아래쪽에 다른 조각이 있거나
                    # 2) 여러 조각이 있거나
                    # 3) 조각 1개라도 필요한 높이가 영역 높이보다 작으면 트리밍 필요
                    needs_cut = (len(pieces_below) > 0 or
                               len(pieces_with_height) > 1 or
                               (len(pieces_with_height) == 1 and req_h < region.height - 1))

                    if needs_cut:
                        trimming_cuts.append({
                            'type': 'horizontal',
                            'position': cut_y,
                            'affects': len(affected_pieces),
                            'priority': 1000 + len(affected_pieces)
                        })

        # 수직 절단선: 같은 x 시작점의 조각들을 너비별로 sub-group화하여 트리밍
        # 먼저 x 시작점별로 그룹화
        x_groups = {}
        for piece in region.pieces:
            x_start = piece['x']
            if x_start not in x_groups:
                x_groups[x_start] = []
            x_groups[x_start].append(piece)

        # 각 x 그룹을 너비별로 sub-group화
        for x_start, pieces_at_x in x_groups.items():
            # 너비별로 sub-group 생성
            width_subgroups = {}
            for p in pieces_at_x:
                p_req_w = p['height'] if p.get('rotated', False) else p['width']
                if p_req_w not in width_subgroups:
                    width_subgroups[p_req_w] = []
                width_subgroups[p_req_w].append(p)

            # 각 너비별 sub-group에 대해 독립적으로 절단선 생성
            for req_w, pieces_with_width in width_subgroups.items():
                cut_x = x_start + req_w

                if region.x < cut_x < region.x + region.width:
                    # 이 절단으로 영향받는 조각들 (같은 너비를 가진 조각들만)
                    affected_pieces = pieces_with_width

                    # 왼쪽에 다른 조각이 있는지 확인
                    pieces_left = []
                    for p in region.pieces:
                        if p not in pieces_with_width:  # 다른 너비 또는 다른 x
                            p_req_w = p['height'] if p.get('rotated', False) else p['width']
                            actual_w = p.get('placed_w', p_req_w)
                            if p['x'] + actual_w <= cut_x:
                                pieces_left.append(p)

                    # 절단이 필요한 경우:
                    # 1) 왼쪽에 다른 조각이 있거나
                    # 2) 여러 조각이 있거나
                    # 3) 조각 1개라도 필요한 너비가 영역 너비보다 작으면 트리밍 필요
                    needs_cut = (len(pieces_left) > 0 or
                               len(pieces_with_width) > 1 or
                               (len(pieces_with_width) == 1 and req_w < region.width - 1))

                    if needs_cut:
                        trimming_cuts.append({
                            'type': 'vertical',
                            'position': cut_x,
                            'affects': len(affected_pieces),
                            'priority': 1000 + len(affected_pieces)
                        })

        return trimming_cuts

    def _generate_separation_cuts(self, region):
        """이미 트림된 조각들을 분리하는 절단선 생성"""
        separation_cuts = []

        # 수평 분리선: 조각의 하단 + kerf 위치
        y_separators = set()
        for piece in region.pieces:
            # 회전 고려: 실제 배치된 높이 사용
            req_h = piece['width'] if piece.get('rotated', False) else piece['height']
            sep_y = piece['y'] + req_h + self.kerf
            # 영역 내부이고, 다른 조각과의 경계인 경우
            if region.y < sep_y < region.y + region.height:
                y_separators.add(sep_y)

        for sep_y in y_separators:
            # 이 절단선이 실제로 조각들을 분리하는지 확인
            above = [p for p in region.pieces if p['y'] >= sep_y]
            below = []
            for p in region.pieces:
                req_h = p['width'] if p.get('rotated', False) else p['height']
                if p['y'] + req_h < sep_y:
                    below.append(p)

            if len(above) > 0 and len(below) > 0:
                separation_cuts.append({
                    'type': 'horizontal',
                    'position': sep_y,
                    'affects': 1,
                    'priority': min(len(above), len(below))  # 균형 잡힌 분리 우선
                })

        # 수직 분리선: 조각의 우측 + kerf 위치
        x_separators = set()
        for piece in region.pieces:
            # 회전 고려: 실제 배치된 너비 사용
            req_w = piece['height'] if piece.get('rotated', False) else piece['width']
            sep_x = piece['x'] + req_w + self.kerf
            # 영역 내부이고, 다른 조각과의 경계인 경우
            if region.x < sep_x < region.x + region.width:
                x_separators.add(sep_x)

        for sep_x in x_separators:
            # 이 절단선이 실제로 조각들을 분리하는지 확인
            right = [p for p in region.pieces if p['x'] >= sep_x]
            left = []
            for p in region.pieces:
                req_w = p['height'] if p.get('rotated', False) else p['width']
                if p['x'] + req_w < sep_x:
                    left.append(p)

            if len(right) > 0 and len(left) > 0:
                separation_cuts.append({
                    'type': 'vertical',
                    'position': sep_x,
                    'affects': 1,
                    'priority': min(len(right), len(left))  # 균형 잡힌 분리 우선
                })

        return separation_cuts

    def _split_region(self, region, cuts, cut_order):
        """영역을 재귀적으로 분할 (차원 트리밍 우선)"""
        # 조각이 없으면 종료
        if not region.pieces:
            return

        # 모든 조각이 정확한 크기면 분리만 수행
        all_exact = self._all_pieces_exact(region)

        if all_exact:
            # 조각이 1개보다 많으면 분리 필요
            if len(region.pieces) <= 1:
                return
            # 트리밍은 필요없고 분리만 필요
            trimming_cuts = []
        else:
            # Phase 1: 트리밍 절단선 생성 (정확한 크기 아닐 때만)
            trimming_cuts = self._generate_trimming_cuts(region)

        # Phase 2: 분리 절단선 생성 (항상)
        separation_cuts = self._generate_separation_cuts(region)

        # 우선순위로 정렬
        # 1순위: 트리밍(1000+) vs 분리(낮음)
        # 2순위: 같은 타입 내에서는 position이 작은 것 먼저 (아래→위, 왼→오)
        #        이유: 같은 시작점에서 다른 높이 조각들이 있을 때 작은 높이를 먼저 분리
        all_cuts = sorted(
            trimming_cuts + separation_cuts,
            key=lambda c: (c['priority'], -c['position']),  # priority 높은 순, position 낮은 순
            reverse=True
        )

        # 절단선이 없으면 종료
        if not all_cuts:
            return

        # 최우선 절단 선택
        best_cut = all_cuts[0]

        # 절단 실행
        if best_cut['type'] == 'horizontal':
            # 수평 절단: 조각들을 위/아래로 분할
            above = [p for p in region.pieces if p['y'] >= best_cut['position']]
            below = []
            for p in region.pieces:
                # 현재 실제 배치된 높이 사용
                actual_h = p.get('placed_h', p['width'] if p.get('rotated') else p['height'])
                if p['y'] + actual_h <= best_cut['position']:
                    below.append(p)

            # 절단선이 조각들을 올바르게 분리하는지 확인
            if len(above) + len(below) != len(region.pieces):
                # 일부 조각이 절단선을 가로지름 - 트리밍 절단
                # 절단선 아래쪽에 걸친 조각들의 placed_h 업데이트
                for piece in region.pieces:
                    actual_h = piece.get('placed_h', piece['width'] if piece.get('rotated') else piece['height'])
                    if piece['y'] < best_cut['position'] <= piece['y'] + actual_h:
                        # placed_h가 이미 정확하게 설정된 경우 덮어쓰지 않음
                        req_h = piece['width'] if piece.get('rotated', False) else piece['height']
                        if 'placed_h' in piece and abs(piece['placed_h'] - req_h) <= 1:
                            continue  # 이미 정확한 크기
                        piece['placed_h'] = best_cut['position'] - piece['y']

                # 다시 분류 - 트리밍된 조각을 어느 영역에 배치할지 결정
                above = []
                below = []
                for p in region.pieces:
                    if p['y'] >= best_cut['position']:
                        above.append(p)
                    else:
                        # 아래쪽에 시작하는 조각
                        actual_h = p.get('placed_h', p['width'] if p.get('rotated') else p['height'])
                        req_h = p['width'] if p.get('rotated', False) else p['height']

                        # 트리밍 후에도 여전히 더 필요한 경우 → above 영역에서 계속 처리
                        if actual_h < req_h - 1:  # 1mm 오차 허용
                            above.append(p)
                        # 정확한 크기가 되었거나 아래쪽에 완전히 속하는 경우
                        elif p['y'] + actual_h <= best_cut['position']:
                            below.append(p)
                        # 그 외의 경우도 above에서 처리
                        else:
                            above.append(p)

            cuts.append({
                'order': cut_order[0],
                'direction': 'H',
                'position': best_cut['position'],
                'start': region.x,
                'end': region.x + region.width,
                'region_x': region.x,
                'region_y': region.y,
                'region_w': region.width,
                'region_h': region.height
            })
            cut_order[0] += 1

            # 하위 영역 생성
            if len(below) > 0:
                below_region = Region(
                    region.x,
                    region.y,
                    region.width,
                    best_cut['position'] - region.y
                )
                below_region.pieces = below

                # 영역 경계에 정확히 맞는 조각들의 placed_h 설정
                for piece in below:
                    req_h = piece['width'] if piece.get('rotated', False) else piece['height']
                    # 조각이 영역을 꽉 채우는 경우 (y 시작점 + 필요 높이 = 영역 끝)
                    if piece['y'] == below_region.y and abs(piece['y'] + req_h - (below_region.y + below_region.height)) <= 1:
                        piece['placed_h'] = req_h

                self._split_region(below_region, cuts, cut_order)

            if len(above) > 0:
                above_region = Region(
                    region.x,
                    best_cut['position'],
                    region.width,
                    region.y + region.height - best_cut['position']
                )
                above_region.pieces = above

                # 영역 경계에 정확히 맞는 조각들의 placed_h 설정
                for piece in above:
                    req_h = piece['width'] if piece.get('rotated', False) else piece['height']
                    # 조각이 영역을 꽉 채우는 경우 (y 시작점 + 필요 높이 = 영역 끝)
                    if piece['y'] == above_region.y and abs(piece['y'] + req_h - (above_region.y + above_region.height)) <= 1:
                        piece['placed_h'] = req_h

                self._split_region(above_region, cuts, cut_order)

        else:  # 수직 절단
            right = [p for p in region.pieces if p['x'] >= best_cut['position']]
            left = []
            for p in region.pieces:
                # 현재 실제 배치된 너비 사용
                actual_w = p.get('placed_w', p['height'] if p.get('rotated') else p['width'])
                if p['x'] + actual_w <= best_cut['position']:
                    left.append(p)

            # 절단선이 조각들을 올바르게 분리하는지 확인
            if len(right) + len(left) != len(region.pieces):
                # 일부 조각이 절단선을 가로지름 - 트리밍 절단
                # 절단선 좌측에 걸친 조각들의 placed_w 업데이트
                for piece in region.pieces:
                    actual_w = piece.get('placed_w', piece['height'] if piece.get('rotated') else piece['width'])
                    if piece['x'] < best_cut['position'] <= piece['x'] + actual_w:
                        # placed_w가 이미 정확하게 설정된 경우 덮어쓰지 않음
                        req_w = piece['height'] if piece.get('rotated', False) else piece['width']
                        if 'placed_w' in piece and abs(piece['placed_w'] - req_w) <= 1:
                            continue  # 이미 정확한 크기
                        piece['placed_w'] = best_cut['position'] - piece['x']

                # 다시 분류 - 트리밍된 조각을 어느 영역에 배치할지 결정
                right = []
                left = []
                for p in region.pieces:
                    if p['x'] >= best_cut['position']:
                        right.append(p)
                    else:
                        # 왼쪽에 시작하는 조각
                        actual_w = p.get('placed_w', p['height'] if p.get('rotated') else p['width'])
                        req_w = p['height'] if p.get('rotated', False) else p['width']

                        # 트리밍 후에도 여전히 더 필요한 경우 → right 영역에서 계속 처리
                        if actual_w < req_w - 1:  # 1mm 오차 허용
                            right.append(p)
                        # 정확한 크기가 되었거나 왼쪽에 완전히 속하는 경우
                        elif p['x'] + actual_w <= best_cut['position']:
                            left.append(p)
                        # 그 외의 경우도 right에서 처리
                        else:
                            right.append(p)

            cuts.append({
                'order': cut_order[0],
                'direction': 'V',
                'position': best_cut['position'],
                'start': region.y,
                'end': region.y + region.height,
                'region_x': region.x,
                'region_y': region.y,
                'region_w': region.width,
                'region_h': region.height
            })
            cut_order[0] += 1

            # 하위 영역 생성
            if len(left) > 0:
                left_region = Region(
                    region.x,
                    region.y,
                    best_cut['position'] - region.x,
                    region.height
                )
                left_region.pieces = left

                # 영역 경계에 정확히 맞는 조각들의 placed_w 설정
                for piece in left:
                    req_w = piece['height'] if piece.get('rotated', False) else piece['width']
                    # 조각이 영역을 꽉 채우는 경우 (x 시작점 + 필요 너비 = 영역 끝)
                    if piece['x'] == left_region.x and abs(piece['x'] + req_w - (left_region.x + left_region.width)) <= 1:
                        piece['placed_w'] = req_w

                self._split_region(left_region, cuts, cut_order)

            if len(right) > 0:
                right_region = Region(
                    best_cut['position'],
                    region.y,
                    region.x + region.width - best_cut['position'],
                    region.height
                )
                right_region.pieces = right

                # 영역 경계에 정확히 맞는 조각들의 placed_w 설정
                for piece in right:
                    req_w = piece['height'] if piece.get('rotated', False) else piece['width']
                    # 조각이 영역을 꽉 채우는 경우 (x 시작점 + 필요 너비 = 영역 끝)
                    if piece['x'] == right_region.x and abs(piece['x'] + req_w - (right_region.x + right_region.width)) <= 1:
                        piece['placed_w'] = req_w

                self._split_region(right_region, cuts, cut_order)
