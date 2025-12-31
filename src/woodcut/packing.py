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
        self.required_cuts = []  # 배치 단계에서 생성된 필수 절단선 힌트


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

        # 배치 단계에서 생성된 필수 절단선 전달
        if 'required_cuts' in plate:
            root_region.required_cuts = plate['required_cuts']

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

    def _all_pieces_exact_height(self, region):
        """영역 내 모든 조각의 높이가 정확한지 확인"""
        for piece in region.pieces:
            if 'placed_h' not in piece:
                return False

            actual_h = piece['placed_h']
            required_h = piece['width'] if piece.get('rotated', False) else piece['height']

            if abs(actual_h - required_h) > 1:
                return False
        return True

    def _generate_height_boundary_separation_cuts(self, region):
        """
        required_h가 다른 조각들 사이의 수직 경계 찾기
        (높이 경계 separation - 수직 절단)

        중요: 같은 y 위치(수평 라인)에 있는 조각들만 비교
        """
        cuts = []

        # y 위치별로 조각 그룹화
        y_groups = {}
        for piece in region.pieces:
            y = piece['y']
            if y not in y_groups:
                y_groups[y] = []
            y_groups[y].append(piece)

        # 각 y 라인에서 x 경계 찾기
        for y_start, pieces_at_y in y_groups.items():
            x_positions = set()

            # 이 y 라인의 오른쪽 경계 수집
            for piece in pieces_at_y:
                req_w = piece['height'] if piece.get('rotated', False) else piece['width']
                x_positions.add(piece['x'] + req_w)

            for sep_x in x_positions:
                # 경계선 양쪽의 조각들 찾기 (같은 y에서만)
                left_edge = [
                    p for p in pieces_at_y
                    if abs(p['x'] + (p['height'] if p.get('rotated', False) else p['width']) - sep_x) < 1
                ]
                right_edge = [
                    p for p in pieces_at_y
                    if abs(p['x'] - (sep_x + self.kerf)) < 1
                ]

                # 양쪽 required_h 수집
                left_heights = set()
                right_heights = set()

                for p in left_edge:
                    req_h = p['width'] if p.get('rotated', False) else p['height']
                    left_heights.add(req_h)

                for p in right_edge:
                    req_h = p['width'] if p.get('rotated', False) else p['height']
                    right_heights.add(req_h)

                # required_h가 다르면 경계로 인식
                if left_heights and right_heights and left_heights != right_heights:
                    cuts.append({
                        'direction': 'V',
                        'position': sep_x,
                        'start': region.y,
                        'end': region.y + region.height
                    })

        return cuts

    def _generate_height_trimming_cuts(self, region):
        """
        높이(placed_h) trimming cuts 생성
        - 회전 안 함: 수평 절단 (H)
        - 회전함: 수직 절단 (V)

        중요: 같은 y 라인의 조각들만 trim (start/end 제한)
        """
        cuts = []

        # y 위치별로 조각 그룹화
        y_groups = {}
        for piece in region.pieces:
            y = piece['y']
            if y not in y_groups:
                y_groups[y] = []
            y_groups[y].append(piece)

        # 각 y 라인에서 height trimming
        for y_start, pieces_at_y in y_groups.items():
            for piece in pieces_at_y:
                req_h = piece['width'] if piece.get('rotated', False) else piece['height']
                actual_h = piece.get('placed_h', piece['height'])

                # 높이가 이미 정확하면 스킵
                if abs(actual_h - req_h) <= 1:
                    continue

                # 회전 여부에 따라 절단 방향 결정
                if piece.get('rotated', False):
                    # 회전됨: height는 가로(x축) → 수직 절단
                    cut_pos = piece['x'] + req_h
                    if region.x < cut_pos < region.x + region.width:
                        # 이 y 라인의 조각들 범위만
                        y_min = y_start
                        y_max = y_start + max(p.get('placed_h', p['width']) for p in pieces_at_y)
                        cuts.append({
                            'direction': 'V',
                            'position': cut_pos,
                            'start': y_min,
                            'end': y_max
                        })
                else:
                    # 회전 안 함: height는 세로(y축) → 수평 절단
                    cut_pos = piece['y'] + req_h
                    if region.y < cut_pos < region.y + region.height:
                        cuts.append({
                            'direction': 'H',
                            'position': cut_pos,
                            'start': region.x,
                            'end': region.x + region.width
                        })

        return cuts

    def _generate_width_boundary_separation_cuts(self, region):
        """
        required_w가 다른 조각들 사이의 수평 경계 찾기
        (너비 경계 separation - 수평 절단)

        중요: 같은 x 위치(수직 라인)에 있는 조각들만 비교
        """
        cuts = []

        # x 위치별로 조각 그룹화
        x_groups = {}
        for piece in region.pieces:
            x = piece['x']
            if x not in x_groups:
                x_groups[x] = []
            x_groups[x].append(piece)

        # 각 x 라인에서 y 경계 찾기
        for x_start, pieces_at_x in x_groups.items():
            y_positions = set()

            # 이 x 라인의 위쪽 경계 수집
            for piece in pieces_at_x:
                req_h = piece['width'] if piece.get('rotated', False) else piece['height']
                y_positions.add(piece['y'] + req_h)

            for sep_y in y_positions:
                # 경계선 위아래의 조각들 찾기 (같은 x에서만)
                bottom_edge = [
                    p for p in pieces_at_x
                    if abs(p['y'] + (p['width'] if p.get('rotated', False) else p['height']) - sep_y) < 1
                ]
                top_edge = [
                    p for p in pieces_at_x
                    if abs(p['y'] - (sep_y + self.kerf)) < 1
                ]

                # 위아래 required_w 수집
                bottom_widths = set()
                top_widths = set()

                for p in bottom_edge:
                    req_w = p['height'] if p.get('rotated', False) else p['width']
                    bottom_widths.add(req_w)

                for p in top_edge:
                    req_w = p['height'] if p.get('rotated', False) else p['width']
                    top_widths.add(req_w)

                # required_w가 다르면 경계로 인식
                if bottom_widths and top_widths and bottom_widths != top_widths:
                    cuts.append({
                        'direction': 'H',
                        'position': sep_y,
                        'start': region.x,
                        'end': region.x + region.width
                    })

        return cuts

    def _generate_width_trimming_cuts(self, region):
        """
        너비(placed_w) trimming cuts 생성
        - 회전 안 함: 수직 절단 (V)
        - 회전함: 수평 절단 (H)

        중요: 같은 x 라인의 조각들만 trim (start/end 제한)
        """
        cuts = []

        # x 위치별로 조각 그룹화
        x_groups = {}
        for piece in region.pieces:
            x = piece['x']
            if x not in x_groups:
                x_groups[x] = []
            x_groups[x].append(piece)

        # 각 x 라인에서 width trimming
        for x_start, pieces_at_x in x_groups.items():
            for piece in pieces_at_x:
                req_w = piece['height'] if piece.get('rotated', False) else piece['width']
                actual_w = piece.get('placed_w', piece['width'])

                # 너비가 이미 정확하면 스킵
                if abs(actual_w - req_w) <= 1:
                    continue

                # 회전 여부에 따라 절단 방향 결정
                if piece.get('rotated', False):
                    # 회전됨: width는 세로(y축) → 수평 절단
                    cut_pos = piece['y'] + req_w
                    if region.y < cut_pos < region.y + region.height:
                        cuts.append({
                            'direction': 'H',
                            'position': cut_pos,
                            'start': region.x,
                            'end': region.x + region.width
                        })
                else:
                    # 회전 안 함: width는 가로(x축) → 수직 절단
                    cut_pos = piece['x'] + req_w
                    if region.x < cut_pos < region.x + region.width:
                        # 이 x 라인의 조각들 범위만
                        x_min = x_start
                        x_max = x_start + max(p.get('placed_w', p['width']) for p in pieces_at_x)
                        cuts.append({
                            'direction': 'V',
                            'position': cut_pos,
                            'start': region.y,
                            'end': region.y + region.height
                        })

        return cuts

    def _generate_final_separation_cuts(self, region):
        """
        모든 trimming 완료 후 조각들을 개별 분리하는 절단선 생성
        (조각 간 kerf 간격으로 분리)
        """
        cuts = []

        # 모든 조각의 오른쪽 경계 수집 (수직 절단)
        for piece in region.pieces:
            req_w = piece['height'] if piece.get('rotated', False) else piece['width']
            sep_x = piece['x'] + req_w

            # 영역 내부이고, 오른쪽에 다른 조각이 있는지 확인
            if region.x < sep_x < region.x + region.width:
                # 이 절단선 오른쪽에 조각이 있는지
                has_right = any(
                    p['x'] >= sep_x + self.kerf
                    for p in region.pieces
                    if p is not piece
                )

                if has_right:
                    cuts.append({
                        'direction': 'V',
                        'position': sep_x,
                        'start': region.y,
                        'end': region.y + region.height
                    })

        # 모든 조각의 위쪽 경계 수집 (수평 절단)
        for piece in region.pieces:
            req_h = piece['width'] if piece.get('rotated', False) else piece['height']
            sep_y = piece['y'] + req_h

            # 영역 내부이고, 위쪽에 다른 조각이 있는지 확인
            if region.y < sep_y < region.y + region.height:
                # 이 절단선 위쪽에 조각이 있는지
                has_top = any(
                    p['y'] >= sep_y + self.kerf
                    for p in region.pieces
                    if p is not piece
                )

                if has_top:
                    cuts.append({
                        'direction': 'H',
                        'position': sep_y,
                        'start': region.x,
                        'end': region.x + region.width
                    })

        return cuts

    def _split_pieces_horizontal(self, region, y_cut):
        """조각들을 수평 절단선 기준으로 분리 (글로벌 좌표, 원본 참조 유지)"""
        bottom = []
        top = []

        for piece in region.pieces:
            # placed_h 사용 (trimming 후)
            piece_h = piece.get('placed_h', piece['width'] if piece.get('rotated', False) else piece['height'])
            piece_y_end = piece['y'] + piece_h

            if piece_y_end <= y_cut:
                bottom.append(piece)  # 원본 참조 유지
            elif piece['y'] >= y_cut + self.kerf:
                top.append(piece)  # 원본 참조 유지
            # else: 절단선에 걸친 조각 없음 (trimming 완료 후 호출)

        return top, bottom

    def _split_pieces_vertical(self, region, x_cut):
        """조각들을 수직 절단선 기준으로 분리 (글로벌 좌표, 원본 참조 유지)"""
        left = []
        right = []

        for piece in region.pieces:
            # placed_w 사용 (trimming 후)
            piece_w = piece.get('placed_w', piece['height'] if piece.get('rotated', False) else piece['width'])
            piece_x_end = piece['x'] + piece_w

            if piece_x_end <= x_cut:
                left.append(piece)  # 원본 참조 유지
            elif piece['x'] >= x_cut + self.kerf:
                right.append(piece)  # 원본 참조 유지

        return left, right

    def _execute_cut_and_recurse(self, region, cut, cuts, cut_order, is_trimming=False):
        """절단 실행 및 양쪽 영역 재귀"""
        # 절단선 저장 (글로벌 좌표)
        cuts.append({
            'order': cut_order[0],
            'direction': cut['direction'],
            'position': cut['position'],
            'start': cut['start'],
            'end': cut['end'],
            'region_x': region.x,
            'region_y': region.y,
            'region_w': region.width,
            'region_h': region.height
        })
        cut_order[0] += 1

        # Trimming cut일 경우 조각의 placed_h/w 업데이트
        if is_trimming:
            for piece in region.pieces:
                req_h = piece['width'] if piece.get('rotated', False) else piece['height']
                req_w = piece['height'] if piece.get('rotated', False) else piece['width']

                # H 방향 절단: 조각이 절단선 아래에 걸침
                if cut['direction'] == 'H':
                    # 절단선 범위 내의 조각만 (start <= x < end)
                    if not (cut['start'] <= piece['x'] < cut['end']):
                        continue

                    if piece['y'] < cut['position'] <= piece['y'] + piece.get('placed_h', piece['height']):
                        # 회전 안 함: height trimming
                        if not piece.get('rotated', False):
                            piece['placed_h'] = cut['position'] - piece['y']
                        # 회전함: width trimming
                        else:
                            piece['placed_w'] = cut['position'] - piece['y']

                # V 방향 절단: 조각이 절단선 왼쪽에 걸침
                elif cut['direction'] == 'V':
                    # 절단선 범위 내의 조각만 (start <= y < end)
                    if not (cut['start'] <= piece['y'] < cut['end']):
                        continue

                    if piece['x'] < cut['position'] <= piece['x'] + piece.get('placed_w', piece['width']):
                        # 회전 안 함: width trimming
                        if not piece.get('rotated', False):
                            piece['placed_w'] = cut['position'] - piece['x']
                        # 회전함: height trimming
                        else:
                            piece['placed_h'] = cut['position'] - piece['x']

        # 영역 분할
        if cut['direction'] == 'H':
            # 수평 절단: 조각들을 위/아래로 분리 (글로벌 좌표)
            top_pieces, bottom_pieces = self._split_pieces_horizontal(region, cut['position'])

            # 하단 영역
            if bottom_pieces:
                bottom_region = Region(
                    x=region.x,
                    y=region.y,
                    width=region.width,
                    height=cut['position'] - region.y
                )
                bottom_region.pieces = bottom_pieces
                bottom_region.required_cuts = region.required_cuts  # 필수 절단선 전달
                self._split_region(bottom_region, cuts, cut_order)

            # 상단 영역
            if top_pieces:
                top_region = Region(
                    x=region.x,
                    y=cut['position'] + self.kerf,
                    width=region.width,
                    height=region.y + region.height - (cut['position'] + self.kerf)
                )
                top_region.pieces = top_pieces
                top_region.required_cuts = region.required_cuts  # 필수 절단선 전달
                self._split_region(top_region, cuts, cut_order)

        else:  # 'V'
            # 수직 절단: 조각들을 좌/우로 분리 (글로벌 좌표)
            left_pieces, right_pieces = self._split_pieces_vertical(region, cut['position'])

            # 좌측 영역
            if left_pieces:
                left_region = Region(
                    x=region.x,
                    y=region.y,
                    width=cut['position'] - region.x,
                    height=region.height
                )
                left_region.pieces = left_pieces
                left_region.required_cuts = region.required_cuts  # 필수 절단선 전달
                self._split_region(left_region, cuts, cut_order)

            # 우측 영역
            if right_pieces:
                right_region = Region(
                    x=cut['position'] + self.kerf,
                    y=region.y,
                    width=region.x + region.width - (cut['position'] + self.kerf),
                    height=region.height
                )
                right_region.pieces = right_pieces
                right_region.required_cuts = region.required_cuts  # 필수 절단선 전달
                self._split_region(right_region, cuts, cut_order)

    def _split_region(self, region, cuts, cut_order):
        """FSM 기반 영역 재귀 분할 (글로벌 좌표 유지)"""
        # 종료 조건: 조각 없음
        if not region.pieces:
            return

        # 조각이 1개이고 placed_w/h가 정확하면 종료
        if len(region.pieces) == 1:
            piece = region.pieces[0]
            req_w = piece['height'] if piece.get('rotated', False) else piece['width']
            req_h = piece['width'] if piece.get('rotated', False) else piece['height']

            # placed_w/h 설정 (없으면)
            if 'placed_w' not in piece:
                piece['placed_w'] = req_w
            if 'placed_h' not in piece:
                piece['placed_h'] = req_h

            # 이미 정확한 크기면 종료
            actual_w = piece.get('placed_w', req_w)
            actual_h = piece.get('placed_h', req_h)

            if abs(actual_w - req_w) <= 1 and abs(actual_h - req_h) <= 1:
                return
            # 아니면 trimming 계속

        # Phase 0: 배치 단계에서 지정한 필수 절단선 (최우선, 순서 유지)
        if region.required_cuts:
            # 영역 내부에 해당하는 첫 번째 절단선 실행
            for i, cut_hint in enumerate(region.required_cuts):
                is_valid = False

                if cut_hint['direction'] == 'V':
                    # 수직: x 좌표가 영역 내부인지
                    if region.x < cut_hint['position'] < region.x + region.width:
                        cut = {
                            'direction': 'V',
                            'position': cut_hint['position'],
                            'start': max(cut_hint['start'], region.y),
                            'end': min(cut_hint['end'], region.y + region.height)
                        }
                        is_valid = True
                else:  # 'H'
                    # 수평: y 좌표가 영역 내부인지
                    if region.y < cut_hint['position'] < region.y + region.height:
                        cut = {
                            'direction': 'H',
                            'position': cut_hint['position'],
                            'start': max(cut_hint['start'], region.x),
                            'end': min(cut_hint['end'], region.x + region.width)
                        }
                        is_valid = True

                if is_valid:
                    # 사용한 절단선 제거
                    region.required_cuts.pop(i)

                    self._execute_cut_and_recurse(region, cut, cuts, cut_order)
                    return

        # Phase 1-1: Height Boundary Separation (required_h 경계)
        h_sep_cuts = self._generate_height_boundary_separation_cuts(region)
        if h_sep_cuts:
            # 가장 왼쪽 경계 1개만 선택
            cut = min(h_sep_cuts, key=lambda c: c['position'])
            self._execute_cut_and_recurse(region, cut, cuts, cut_order)
            return

        # Phase 1-2: Height Trimming (placed_h 조정)
        if not self._all_pieces_exact_height(region):
            h_cuts = self._generate_height_trimming_cuts(region)
            if h_cuts:
                # 가장 아래쪽 trim 1개만 선택 (작은 y부터)
                cut = min(h_cuts, key=lambda c: c['position'])
                self._execute_cut_and_recurse(region, cut, cuts, cut_order, is_trimming=True)
                return

        # Phase 2-1: Width Boundary Separation (required_w 경계)
        w_sep_cuts = self._generate_width_boundary_separation_cuts(region)
        if w_sep_cuts:
            # 가장 아래쪽 경계 1개만 선택
            cut = min(w_sep_cuts, key=lambda c: c['position'])
            self._execute_cut_and_recurse(region, cut, cuts, cut_order)
            return

        # Phase 2-2: Width Trimming (placed_w 조정)
        if not self._all_pieces_exact(region):  # width도 체크
            w_cuts = self._generate_width_trimming_cuts(region)
            if w_cuts:
                # 가장 왼쪽 trim 1개만 선택
                cut = min(w_cuts, key=lambda c: c['position'])
                self._execute_cut_and_recurse(region, cut, cuts, cut_order, is_trimming=True)
                return

        # Phase 3: Final Separation (조각이 2개 이상이면 분리)
        if len(region.pieces) > 1:
            # 조각 간 kerf 간격으로 분리
            sep_cuts = self._generate_final_separation_cuts(region)
            if sep_cuts:
                # 가장 왼쪽/아래 separation 1개만 선택
                cut = min(sep_cuts, key=lambda c: c['position'])
                self._execute_cut_and_recurse(region, cut, cuts, cut_order)
                return

        # DONE: 조각이 1개 또는 모든 조각이 정확한 크기
        return
