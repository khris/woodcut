#!/usr/bin/env python3
"""
MDF 재단 최적화 - 실제 Guillotine Cut 시퀀스
- Guillotine Cut: 영역 전체를 관통
- 높이가 다르면 각 높이마다 절단선
- 분할된 영역 내에서만 절단
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import Rectangle as MPLRect
from matplotlib import font_manager
import platform
from abc import ABC, abstractmethod
import random

def setup_korean_font():
    system = platform.system()
    if system == 'Darwin':
        fonts = ['AppleGothic', 'AppleSDGothicNeo', 'Nanum Gothic']
    elif system == 'Windows':
        fonts = ['Malgun Gothic', 'NanumGothic', 'Gulim']
    else:
        fonts = ['NanumGothic', 'Noto Sans CJK KR', 'UnDotum']
    
    available_fonts = [f.name for f in font_manager.fontManager.ttflist]
    for font in fonts:
        if font in available_fonts:
            plt.rcParams['font.family'] = font
            print(f"폰트 설정: {font}")
            return
    print("⚠️  한글 폰트를 찾지 못했습니다.")

setup_korean_font()
plt.rcParams['axes.unicode_minus'] = False


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

    def __init__(self, plate_width, plate_height, kerf=5, allow_rotation=True):
        self.plate_width = plate_width
        self.plate_height = plate_height
        self.kerf = kerf
        self.allow_rotation = allow_rotation
    
    @abstractmethod
    def pack(self, pieces):
        pass
    
    def expand_pieces(self, pieces):
        """조각을 개별 아이템으로 확장"""
        all_pieces = []
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

        # 수평 절단선: 같은 y 시작점의 조각들 중 최대 높이로 절단
        # 먼저 y 시작점별로 그룹화
        y_groups = {}
        for piece in region.pieces:
            y_start = piece['y']
            if y_start not in y_groups:
                y_groups[y_start] = []
            y_groups[y_start].append(piece)

        # 각 y 그룹에 대해 최대 필요 높이 찾기
        for y_start, pieces_at_y in y_groups.items():
            max_req_h = 0
            for p in pieces_at_y:
                p_req_h = p['width'] if p.get('rotated', False) else p['height']
                max_req_h = max(max_req_h, p_req_h)
                # 디버그: 조각 정보 출력
                # print(f"  DEBUG: piece at y={p['y']}, size={p['width']}×{p['height']}, rotated={p.get('rotated')}, req_h={p_req_h}, placed_h={p.get('placed_h', 'None')}")

            cut_y = y_start + max_req_h
            # 디버그: 계산된 절단 위치
            # print(f"DEBUG TRIM: y_group at {y_start}, max_req_h={max_req_h}, cut_y={cut_y}, region=({region.x},{region.y} {region.width}×{region.height})")

            if region.y < cut_y < region.y + region.height:
                # 이 절단으로 영향받는 조각들 (같은 y에서 시작하는 모든 조각)
                affected_pieces = pieces_at_y

                # 아래쪽에 다른 조각이 있는지 확인
                pieces_below = []
                for p in region.pieces:
                    if p not in pieces_at_y:  # 다른 y 시작점
                        p_req_h = p['width'] if p.get('rotated', False) else p['height']
                        actual_h = p.get('placed_h', p_req_h)
                        if p['y'] + actual_h <= cut_y:
                            pieces_below.append(p)

                # 절단이 필요한 경우:
                # 1) 아래쪽에 다른 조각이 있거나
                # 2) 여러 조각이 있거나
                # 3) 조각 1개라도 필요한 높이가 영역 높이보다 작으면 트리밍 필요
                needs_cut = (len(pieces_below) > 0 or
                           len(pieces_at_y) > 1 or
                           (len(pieces_at_y) == 1 and max_req_h < region.height - 1))

                if needs_cut:
                    trimming_cuts.append({
                        'type': 'horizontal',
                        'position': cut_y,
                        'affects': len(affected_pieces),
                        'priority': 1000 + len(affected_pieces)
                    })

        # 수직 절단선: 같은 x 시작점의 조각들 중 최대 너비로 절단
        # 먼저 x 시작점별로 그룹화
        x_groups = {}
        for piece in region.pieces:
            x_start = piece['x']
            if x_start not in x_groups:
                x_groups[x_start] = []
            x_groups[x_start].append(piece)

        # 각 x 그룹에 대해 최대 필요 너비 찾기
        for x_start, pieces_at_x in x_groups.items():
            max_req_w = 0
            for p in pieces_at_x:
                p_req_w = p['height'] if p.get('rotated', False) else p['width']
                max_req_w = max(max_req_w, p_req_w)

            cut_x = x_start + max_req_w

            if region.x < cut_x < region.x + region.width:
                # 이 절단으로 영향받는 조각들 (같은 x에서 시작하는 모든 조각)
                affected_pieces = pieces_at_x

                # 왼쪽에 다른 조각이 있는지 확인
                pieces_left = []
                for p in region.pieces:
                    if p not in pieces_at_x:  # 다른 x 시작점
                        p_req_w = p['height'] if p.get('rotated', False) else p['width']
                        actual_w = p.get('placed_w', p_req_w)
                        if p['x'] + actual_w <= cut_x:
                            pieces_left.append(p)

                # 절단이 필요한 경우:
                # 1) 왼쪽에 다른 조각이 있거나
                # 2) 여러 조각이 있거나
                # 3) 조각 1개라도 필요한 너비가 영역 너비보다 작으면 트리밍 필요
                needs_cut = (len(pieces_left) > 0 or
                           len(pieces_at_x) > 1 or
                           (len(pieces_at_x) == 1 and max_req_w < region.width - 1))

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


class AlignedFreeSpacePacker(PackingStrategy):
    """전략 1: 정렬 우선 자유 공간 패킹"""
    
    def pack(self, pieces):
        all_pieces = self.expand_pieces(pieces)
        all_pieces.sort(key=lambda p: p['area'], reverse=True)

        plates = []
        current_plate = {
            'pieces': [],
            'cuts': [],
            'free_spaces': [FreeSpace(0, 0, self.plate_width, self.plate_height)]
        }

        for piece in all_pieces:
            placement = self._find_best_placement(current_plate, piece)

            if placement:
                self._place_piece(current_plate, piece, placement)
            else:
                plates.append(current_plate)
                current_plate = {
                    'pieces': [],
                    'cuts': [],
                    'free_spaces': [FreeSpace(0, 0, self.plate_width, self.plate_height)]
                }
                placement = self._find_best_placement(current_plate, piece)
                if placement:
                    self._place_piece(current_plate, piece, placement)
        
        if current_plate['pieces']:
            plates.append(current_plate)
        
        for plate in plates:
            self.generate_guillotine_cuts(plate)
        
        return plates
    
    def _find_best_placement(self, plate, piece, preferred_rotation=None):
        w, h = piece['width'], piece['height']

        existing_x = set([0])
        existing_y = set([0])
        for p in plate['pieces']:
            existing_x.add(p['x'])
            # placed_w/h가 아직 없으면 배치 크기 사용
            pw = p.get('placed_w', p['height'] if p.get('rotated') else p['width'])
            ph = p.get('placed_h', p['width'] if p.get('rotated') else p['height'])
            existing_x.add(p['x'] + pw + self.kerf)
            existing_y.add(p['y'])
            existing_y.add(p['y'] + ph + self.kerf)

        candidates = []

        for space in plate['free_spaces']:
            if w + self.kerf <= space.width and h + self.kerf <= space.height:
                x_aligned = 1 if space.x in existing_x else 0
                y_aligned = 1 if space.y in existing_y else 0
                alignment_score = x_aligned + y_aligned
                waste = (space.width - w) * (space.height - h)

                # 선호 방향이면 보너스 (같은 크기 조각 그룹화)
                rotation_bonus = 100 if preferred_rotation is False else 0

                candidates.append({
                    'space': space, 'x': space.x, 'y': space.y,
                    'width': w, 'height': h, 'rotated': False,
                    'alignment_score': alignment_score, 'waste': waste,
                    'rotation_bonus': rotation_bonus
                })

            if self.allow_rotation and h + self.kerf <= space.width and w + self.kerf <= space.height:
                x_aligned = 1 if space.x in existing_x else 0
                y_aligned = 1 if space.y in existing_y else 0
                alignment_score = x_aligned + y_aligned
                waste = (space.width - h) * (space.height - w)

                # 선호 방향이면 보너스 (같은 크기 조각 그룹화)
                rotation_bonus = 100 if preferred_rotation is True else 0

                candidates.append({
                    'space': space, 'x': space.x, 'y': space.y,
                    'width': h, 'height': w, 'rotated': True,
                    'alignment_score': alignment_score, 'waste': waste,
                    'rotation_bonus': rotation_bonus
                })

        if not candidates:
            return None

        candidates.sort(key=lambda c: (-c['rotation_bonus'], -c['alignment_score'], c['waste']))
        return candidates[0]
    
    def _place_piece(self, plate, piece, placement):
        space = placement['space']
        x, y = placement['x'], placement['y']
        w, h = placement['width'], placement['height']
        
        plate['pieces'].append({
            **piece, 'x': x, 'y': y,
            'rotated': placement['rotated']
            # placed_w, placed_h는 절단 알고리즘이 설정
        })
        
        plate['free_spaces'].remove(space)
        
        if space.width > w + self.kerf:
            plate['free_spaces'].append(FreeSpace(
                x + w + self.kerf, y,
                space.width - w - self.kerf, h + self.kerf
            ))
        
        if space.height > h + self.kerf:
            plate['free_spaces'].append(FreeSpace(
                x, y + h + self.kerf,
                space.width, space.height - h - self.kerf
            ))


class GeneticPacker(PackingStrategy):
    """전략 3: 유전 알고리즘"""

    def __init__(self, plate_width, plate_height, kerf=5, allow_rotation=True):
        super().__init__(plate_width, plate_height, kerf, allow_rotation)

    def pack(self, pieces):
        all_pieces = self.expand_pieces(pieces)

        population_size = 20
        generations = 50

        print(f"\n유전 알고리즘: 세대 {generations}개, 개체 {population_size}개")

        # 그룹화된 시퀀스를 초기 population에 포함 (작업 편의성)
        population = []
        grouped_sequence = self._create_grouped_sequence(all_pieces)
        population.append(grouped_sequence)

        # 나머지는 랜덤 (탐색 다양성 유지)
        for _ in range(population_size - 1):
            individual = list(all_pieces)
            random.shuffle(individual)
            population.append(individual)
        
        best_solution = None
        best_score = float('inf')
        
        for gen in range(generations):
            scored_pop = []
            for individual in population:
                result = self._pack_sequence(individual)
                score = self._calculate_score(result)
                scored_pop.append((score, individual, result))
            
            scored_pop.sort(key=lambda x: x[0])
            
            if scored_pop[0][0] < best_score:
                best_score = scored_pop[0][0]
                best_solution = scored_pop[0][2]
            
            if (gen + 1) % 10 == 0:
                print(f"  세대 {gen+1}: 최고 점수 {best_score:.0f}")
            
            survivors = [ind for _, ind, _ in scored_pop[:population_size // 2]]
            new_population = survivors.copy()
            
            while len(new_population) < population_size:
                parent1 = random.choice(survivors)
                parent2 = random.choice(survivors)
                child = self._crossover(parent1, parent2)
                
                if random.random() < 0.1:
                    self._mutate(child)
                
                new_population.append(child)
            
            population = new_population
        
        print(f"  최종 점수: {best_score:.0f}")
        
        for plate in best_solution:
            self.generate_guillotine_cuts(plate)
        
        return best_solution
    
    def _pack_sequence(self, sequence):
        plates = []
        current_plate = {
            'pieces': [],
            'cuts': [],
            'free_spaces': [FreeSpace(0, 0, self.plate_width, self.plate_height)]
        }

        for piece in sequence:
            placement = self._find_placement(current_plate, piece)

            if placement:
                self._place_piece(current_plate, piece, placement)
            else:
                plates.append(current_plate)
                current_plate = {
                    'pieces': [],
                    'cuts': [],
                    'free_spaces': [FreeSpace(0, 0, self.plate_width, self.plate_height)]
                }
                placement = self._find_placement(current_plate, piece)
                if placement:
                    self._place_piece(current_plate, piece, placement)

        if current_plate['pieces']:
            plates.append(current_plate)

        return plates
    
    def _find_placement(self, plate, piece):
        """AlignedFreeSpacePacker와 동일한 정렬 우선 배치"""
        w, h = piece['width'], piece['height']

        # 기존 좌표 수집
        existing_x = set([0])
        existing_y = set([0])
        for p in plate['pieces']:
            existing_x.add(p['x'])
            pw = p.get('placed_w', p['height'] if p.get('rotated') else p['width'])
            ph = p.get('placed_h', p['width'] if p.get('rotated') else p['height'])
            existing_x.add(p['x'] + pw + self.kerf)
            existing_y.add(p['y'])
            existing_y.add(p['y'] + ph + self.kerf)

        candidates = []

        for space in plate['free_spaces']:
            # 일반 방향
            if w + self.kerf <= space.width and h + self.kerf <= space.height:
                x_aligned = 1 if space.x in existing_x else 0
                y_aligned = 1 if space.y in existing_y else 0
                alignment_score = x_aligned + y_aligned
                waste = (space.width - w) * (space.height - h)

                candidates.append({
                    'space': space, 'x': space.x, 'y': space.y,
                    'width': w, 'height': h, 'rotated': False,
                    'alignment_score': alignment_score, 'waste': waste
                })

            # 회전 방향
            if self.allow_rotation and h + self.kerf <= space.width and w + self.kerf <= space.height:
                x_aligned = 1 if space.x in existing_x else 0
                y_aligned = 1 if space.y in existing_y else 0
                alignment_score = x_aligned + y_aligned
                waste = (space.width - h) * (space.height - w)

                candidates.append({
                    'space': space, 'x': space.x, 'y': space.y,
                    'width': h, 'height': w, 'rotated': True,
                    'alignment_score': alignment_score, 'waste': waste
                })

        if not candidates:
            return None

        # 정렬 점수 높은 순, waste 낮은 순
        candidates.sort(key=lambda c: (-c['alignment_score'], c['waste']))
        return candidates[0]
    
    def _place_piece(self, plate, piece, placement):
        space = placement['space']
        x, y = placement['x'], placement['y']
        w, h = placement['width'], placement['height']
        
        plate['pieces'].append({
            **piece, 'x': x, 'y': y,
            'rotated': placement['rotated']
            # placed_w, placed_h는 절단 알고리즘이 설정
        })
        
        plate['free_spaces'].remove(space)
        
        if space.width > w + self.kerf:
            plate['free_spaces'].append(FreeSpace(
                x + w + self.kerf, y,
                space.width - w - self.kerf, h + self.kerf
            ))
        
        if space.height > h + self.kerf:
            plate['free_spaces'].append(FreeSpace(
                x, y + h + self.kerf,
                space.width, space.height - h - self.kerf
            ))
    
    def _calculate_score(self, plates):
        return len(plates) * 10000 + sum(len(p.get('cuts', [])) for p in plates)
    
    def _crossover(self, parent1, parent2):
        size = len(parent1)
        start, end = sorted(random.sample(range(size), 2))
        
        child_middle = parent1[start:end]
        child = [None] * size
        child[start:end] = child_middle
        
        p2_filtered = [p for p in parent2 if p not in child_middle]
        
        j = 0
        for i in range(size):
            if child[i] is None:
                child[i] = p2_filtered[j]
                j += 1
        
        return child
    
    def _mutate(self, individual):
        i, j = random.sample(range(len(individual)), 2)
        individual[i], individual[j] = individual[j], individual[i]

    def _create_grouped_sequence(self, pieces):
        """같은 크기 조각들을 그룹화한 시퀀스 생성 (작업 편의성 향상)"""
        from collections import defaultdict

        groups = defaultdict(list)
        for piece in pieces:
            groups[piece['original']].append(piece)

        # 각 그룹을 면적 기준으로 정렬 (큰 그룹 우선)
        sorted_groups = sorted(
            groups.items(),
            key=lambda item: item[1][0]['area'],
            reverse=True
        )

        result = []
        for _, group_pieces in sorted_groups:
            result.extend(group_pieces)

        return result


class BeamSearchPacker(PackingStrategy):
    """전략 3: Beam Search - 상위 k개 배치 후보 유지"""

    def __init__(self, plate_width, plate_height, kerf=5, allow_rotation=True, beam_width=3):
        super().__init__(plate_width, plate_height, kerf, allow_rotation)
        self.beam_width = beam_width

    def pack(self, pieces):
        all_pieces = self.expand_pieces(pieces)
        all_pieces.sort(key=lambda p: p['area'], reverse=True)

        print(f"\nBeam Search: beam width={self.beam_width}")

        # 초기 빔: 빈 판 1개
        beams = [{
            'plates': [{
                'pieces': [],
                'cuts': [],
                'free_spaces': [FreeSpace(0, 0, self.plate_width, self.plate_height)]
            }],
            'plates_count': 1,
            'score': 0
        }]

        # 각 조각마다
        for piece_idx, piece in enumerate(all_pieces):
            next_beams = []

            # 각 빔에서
            for beam in beams:
                # 현재 판에 배치 시도
                placements = self._find_all_placements(beam, piece)

                for placement in placements:
                    new_beam = self._apply_placement(beam, piece, placement)
                    # 그룹화 점수 계산
                    new_beam['score'] = self._evaluate_beam(new_beam, all_pieces[piece_idx+1:])
                    next_beams.append(new_beam)

                # 새 판 시작 옵션
                if 'plates' in beam and beam['plates'] and beam['plates'][-1]['pieces']:  # 현재 판이 비어있지 않으면
                    new_beam = self._start_new_plate(beam, piece)
                    new_beam['score'] = self._evaluate_beam(new_beam, all_pieces[piece_idx+1:])
                    next_beams.append(new_beam)

            # 상위 beam_width개만 유지
            if next_beams:
                next_beams.sort(key=lambda b: b['score'])
                beams = next_beams[:self.beam_width]
            else:
                # 빔이 없으면 초기화
                beams = [{
                    'plates': [{
                        'pieces': [],
                        'cuts': [],
                        'free_spaces': [FreeSpace(0, 0, self.plate_width, self.plate_height)]
                    }],
                    'plates_count': 1,
                    'score': 0
                }]

        # 최선의 빔 선택
        if not beams:
            return []

        best_beam = beams[0]

        # 판 리스트로 변환
        if 'plates' not in best_beam or not best_beam['plates']:
            return []

        plates = best_beam['plates']

        # Guillotine 절단선 생성
        for plate in plates:
            self.generate_guillotine_cuts(plate)

        return plates

    def _find_all_placements(self, beam, piece):
        """가능한 모든 배치 후보 찾기"""
        w, h = piece['width'], piece['height']
        candidates = []

        # 현재 판이 있으면
        if 'plates' in beam and beam['plates']:
            current_plate = beam['plates'][-1]
        else:
            return candidates  # 판이 없으면 빈 리스트

        # 기존 좌표 수집
        existing_x = set([0])
        existing_y = set([0])
        for p in current_plate['pieces']:
            existing_x.add(p['x'])
            pw = p.get('placed_w', p['height'] if p.get('rotated') else p['width'])
            ph = p.get('placed_h', p['width'] if p.get('rotated') else p['height'])
            existing_x.add(p['x'] + pw + self.kerf)
            existing_y.add(p['y'])
            existing_y.add(p['y'] + ph + self.kerf)

        for space in current_plate['free_spaces']:
            # 일반 방향
            if w + self.kerf <= space.width and h + self.kerf <= space.height:
                x_aligned = 1 if space.x in existing_x else 0
                y_aligned = 1 if space.y in existing_y else 0
                alignment_score = x_aligned + y_aligned
                waste = (space.width - w) * (space.height - h)

                candidates.append({
                    'space': space, 'x': space.x, 'y': space.y,
                    'width': w, 'height': h, 'rotated': False,
                    'alignment_score': alignment_score, 'waste': waste
                })

            # 회전 방향
            if self.allow_rotation and h + self.kerf <= space.width and w + self.kerf <= space.height:
                x_aligned = 1 if space.x in existing_x else 0
                y_aligned = 1 if space.y in existing_y else 0
                alignment_score = x_aligned + y_aligned
                waste = (space.width - h) * (space.height - w)

                candidates.append({
                    'space': space, 'x': space.x, 'y': space.y,
                    'width': h, 'height': w, 'rotated': True,
                    'alignment_score': alignment_score, 'waste': waste
                })

        # 상위 5개만 반환 (너무 많으면 느려짐)
        candidates.sort(key=lambda c: (-c['alignment_score'], c['waste']))
        return candidates[:5]

    def _apply_placement(self, beam, piece, placement):
        """배치 적용하여 새 빔 생성"""
        import copy
        new_beam = copy.deepcopy(beam)

        if 'plates' not in new_beam or not new_beam['plates']:
            new_beam['plates'] = [{
                'pieces': [],
                'cuts': [],
                'free_spaces': [FreeSpace(0, 0, self.plate_width, self.plate_height)]
            }]
            new_beam['plates_count'] = 1

        current_plate = new_beam['plates'][-1]

        # 조각 배치
        space_orig = placement['space']
        x, y = placement['x'], placement['y']
        w, h = placement['width'], placement['height']

        current_plate['pieces'].append({
            **piece, 'x': x, 'y': y,
            'rotated': placement['rotated']
        })

        # 자유 공간 업데이트 - deepcopy로 인해 같은 객체를 찾아야 함
        space = None
        for s in current_plate['free_spaces']:
            if s.x == space_orig.x and s.y == space_orig.y and s.width == space_orig.width and s.height == space_orig.height:
                space = s
                break

        if space:
            current_plate['free_spaces'].remove(space)

            if space.width > w + self.kerf:
                current_plate['free_spaces'].append(FreeSpace(
                    x + w + self.kerf, y,
                    space.width - w - self.kerf, h + self.kerf
                ))

            if space.height > h + self.kerf:
                current_plate['free_spaces'].append(FreeSpace(
                    x, y + h + self.kerf,
                    space.width, space.height - h - self.kerf
                ))

        return new_beam

    def _start_new_plate(self, beam, piece):
        """새 판 시작"""
        import copy
        new_beam = copy.deepcopy(beam)

        if 'plates' not in new_beam:
            new_beam['plates'] = []

        new_beam['plates'].append({
            'pieces': [],
            'cuts': [],
            'free_spaces': [FreeSpace(0, 0, self.plate_width, self.plate_height)]
        })
        new_beam['plates_count'] = len(new_beam['plates'])

        # 첫 조각 배치
        w, h = piece['width'], piece['height']
        new_plate = new_beam['plates'][-1]

        # 회전 고려하여 최선의 방향 선택
        if self.allow_rotation and h < w:
            w, h = h, w
            rotated = True
        else:
            rotated = False

        new_plate['pieces'].append({
            **piece, 'x': 0, 'y': 0,
            'rotated': rotated
        })

        # 자유 공간 업데이트
        new_plate['free_spaces'] = []
        if self.plate_width > w + self.kerf:
            new_plate['free_spaces'].append(FreeSpace(
                w + self.kerf, 0,
                self.plate_width - w - self.kerf, h + self.kerf
            ))
        if self.plate_height > h + self.kerf:
            new_plate['free_spaces'].append(FreeSpace(
                0, h + self.kerf,
                self.plate_width, self.plate_height - h - self.kerf
            ))

        return new_beam

    def _evaluate_beam(self, beam, remaining_pieces):
        """빔 평가 (낮을수록 좋음)"""
        score = 0

        # 1. 판 개수 (가장 중요)
        plates_count = beam.get('plates_count', len(beam.get('plates', [])))
        score += plates_count * 10000

        # 2. 그룹화 점수 (같은 크기가 모여있으면 좋음)
        if 'plates' in beam and beam['plates']:
            for plate in beam['plates']:
                score -= self._calculate_grouping_score(plate['pieces'])

        # 3. 공간 사용률 (높을수록 좋음)
        if 'plates' in beam and beam['plates']:
            for plate in beam['plates']:
                utilization = sum(p['area'] for p in plate['pieces']) / (self.plate_width * self.plate_height)
                score -= utilization * 100

        return score

    def _calculate_grouping_score(self, pieces):
        """그룹화 점수 계산"""
        from collections import defaultdict

        if not pieces:
            return 0

        # 같은 크기 조각들의 연속성 체크
        groups = defaultdict(list)
        for i, piece in enumerate(pieces):
            groups[piece['original']].append(i)

        score = 0
        for original, indices in groups.items():
            if len(indices) <= 1:
                continue
            # 연속된 조각들에 보너스
            for i in range(len(indices) - 1):
                if indices[i+1] - indices[i] == 1:
                    score += 10  # 연속 보너스

        return score


class LookAheadPacker(PackingStrategy):
    """전략 4: Look-ahead 휴리스틱 - 그룹화를 방해하는 배치에 페널티"""

    def pack(self, pieces):
        from collections import defaultdict

        all_pieces = self.expand_pieces(pieces)
        all_pieces.sort(key=lambda p: p['area'], reverse=True)

        # 크기별 그룹 정보 미리 계산
        self.size_groups = defaultdict(int)
        for piece in all_pieces:
            self.size_groups[piece['original']] += 1

        plates = []
        current_plate = {
            'pieces': [],
            'cuts': [],
            'free_spaces': [FreeSpace(0, 0, self.plate_width, self.plate_height)]
        }

        for piece_idx, piece in enumerate(all_pieces):
            # 남은 같은 크기 조각 수 계산
            remaining_same_size = sum(
                1 for p in all_pieces[piece_idx+1:]
                if p['original'] == piece['original']
            )

            placement = self._find_best_placement_lookahead(
                current_plate, piece, remaining_same_size
            )

            if placement:
                self._place_piece(current_plate, piece, placement)
            else:
                plates.append(current_plate)
                current_plate = {
                    'pieces': [],
                    'cuts': [],
                    'free_spaces': [FreeSpace(0, 0, self.plate_width, self.plate_height)]
                }
                placement = self._find_best_placement_lookahead(
                    current_plate, piece, remaining_same_size
                )
                if placement:
                    self._place_piece(current_plate, piece, placement)

        if current_plate['pieces']:
            plates.append(current_plate)

        for plate in plates:
            self.generate_guillotine_cuts(plate)

        return plates

    def _find_best_placement_lookahead(self, plate, piece, remaining_same_size):
        """Look-ahead를 고려한 최적 배치 찾기"""
        w, h = piece['width'], piece['height']

        existing_x = set([0])
        existing_y = set([0])
        for p in plate['pieces']:
            existing_x.add(p['x'])
            pw = p.get('placed_w', p['height'] if p.get('rotated') else p['width'])
            ph = p.get('placed_h', p['width'] if p.get('rotated') else p['height'])
            existing_x.add(p['x'] + pw + self.kerf)
            existing_y.add(p['y'])
            existing_y.add(p['y'] + ph + self.kerf)

        candidates = []

        for space in plate['free_spaces']:
            if w + self.kerf <= space.width and h + self.kerf <= space.height:
                x_aligned = 1 if space.x in existing_x else 0
                y_aligned = 1 if space.y in existing_y else 0
                alignment_score = x_aligned + y_aligned
                waste = (space.width - w) * (space.height - h)

                # Look-ahead 페널티 계산
                lookahead_penalty = self._calculate_lookahead_penalty(
                    plate, space, w, h, False, piece['original'], remaining_same_size
                )

                candidates.append({
                    'space': space, 'x': space.x, 'y': space.y,
                    'width': w, 'height': h, 'rotated': False,
                    'alignment_score': alignment_score, 'waste': waste,
                    'lookahead_penalty': lookahead_penalty
                })

            if self.allow_rotation and h + self.kerf <= space.width and w + self.kerf <= space.height:
                x_aligned = 1 if space.x in existing_x else 0
                y_aligned = 1 if space.y in existing_y else 0
                alignment_score = x_aligned + y_aligned
                waste = (space.width - h) * (space.height - w)

                # Look-ahead 페널티 계산
                lookahead_penalty = self._calculate_lookahead_penalty(
                    plate, space, h, w, True, piece['original'], remaining_same_size
                )

                candidates.append({
                    'space': space, 'x': space.x, 'y': space.y,
                    'width': h, 'height': w, 'rotated': True,
                    'alignment_score': alignment_score, 'waste': waste,
                    'lookahead_penalty': lookahead_penalty
                })

        if not candidates:
            return None

        # 정렬: lookahead_penalty 낮은 순, alignment_score 높은 순, waste 낮은 순
        candidates.sort(key=lambda c: (c['lookahead_penalty'], -c['alignment_score'], c['waste']))
        return candidates[0]

    def _calculate_lookahead_penalty(self, plate, space, w, h, rotated, original_size, remaining_same_size):
        """그룹화를 방해하는 정도 계산"""
        penalty = 0

        # 같은 크기 조각이 더 있으면
        if remaining_same_size > 0:
            # 현재 판에 이미 같은 크기가 있는지 확인
            same_size_in_plate = sum(
                1 for p in plate['pieces']
                if p['original'] == original_size
            )

            # 같은 크기가 이미 있으면 연속 배치 선호 → 페널티 감소
            if same_size_in_plate > 0:
                penalty -= 50

            # 남은 공간이 같은 크기 조각을 더 받기 어려우면 페널티
            remaining_space = space.width * space.height - w * h
            piece_area = w * h

            if remaining_space < piece_area * remaining_same_size:
                penalty += 30  # 그룹화 어려움

        return penalty

    def _place_piece(self, plate, piece, placement):
        space = placement['space']
        x, y = placement['x'], placement['y']
        w, h = placement['width'], placement['height']

        plate['pieces'].append({
            **piece, 'x': x, 'y': y,
            'rotated': placement['rotated']
        })

        plate['free_spaces'].remove(space)

        if space.width > w + self.kerf:
            plate['free_spaces'].append(FreeSpace(
                x + w + self.kerf, y,
                space.width - w - self.kerf, h + self.kerf
            ))

        if space.height > h + self.kerf:
            plate['free_spaces'].append(FreeSpace(
                x, y + h + self.kerf,
                space.width, space.height - h - self.kerf
            ))


class ImprovedGeneticPacker(PackingStrategy):
    """전략 5: 개선된 유전 알고리즘 - 그룹 보존 연산자 + Beam Search 초기화"""

    def __init__(self, plate_width, plate_height, kerf=5, allow_rotation=True):
        super().__init__(plate_width, plate_height, kerf, allow_rotation)

    def pack(self, pieces):
        all_pieces = self.expand_pieces(pieces)

        population_size = 30  # 증가
        generations = 100  # 증가

        print(f"\n개선된 유전 알고리즘: 세대 {generations}개, 개체 {population_size}개")

        # 초기 population: 다양한 전략으로 생성
        population = []

        # 1. 그룹화된 시퀀스 (작업 편의성)
        grouped_sequence = self._create_grouped_sequence(all_pieces)
        population.append(grouped_sequence)

        # 2. 면적 기준 정렬
        area_sorted = sorted(all_pieces, key=lambda p: p['area'], reverse=True)
        population.append(area_sorted)

        # 3. 최소 차원 기준 정렬
        min_dim_sorted = sorted(
            all_pieces,
            key=lambda p: min(p['width'], p['height']),
            reverse=True
        )
        population.append(min_dim_sorted)

        # 4. 나머지는 랜덤
        for _ in range(population_size - 3):
            individual = list(all_pieces)
            random.shuffle(individual)
            population.append(individual)

        best_solution = None
        best_score = float('inf')

        for gen in range(generations):
            # 평가
            scored_population = []
            for individual in population:
                plates = self._pack_sequence(individual)
                score = self._fitness(plates)
                scored_population.append((score, individual, plates))

            scored_population.sort(key=lambda x: x[0])

            if scored_population[0][0] < best_score:
                best_score = scored_population[0][0]
                best_solution = scored_population[0][2]

            if gen % 10 == 0:
                print(f"  세대 {gen}: 최선 점수 = {best_score:.1f}")

            # 선택 (상위 50%)
            population = [ind for _, ind, _ in scored_population[:population_size // 2]]

            # 교배
            while len(population) < population_size:
                parent1, parent2 = random.sample(population[:len(population)//2], 2)
                child = self._crossover_preserve_groups(parent1, parent2)
                population.append(child)

            # 변이 (상위 10%는 보존)
            for i in range(population_size // 10, population_size):
                if random.random() < 0.3:
                    self._mutate_preserve_groups(population[i])

        print(f"  최종 점수: {best_score:.1f}")

        # Guillotine 절단선 생성
        for plate in best_solution:
            self.generate_guillotine_cuts(plate)

        return best_solution

    def _fitness(self, plates):
        """적합도 함수 (낮을수록 좋음)"""
        score = 0

        # 1. 판 개수 (가장 중요)
        score += len(plates) * 100000

        # 2. 절단 횟수
        total_cuts = sum(len(plate['cuts']) for plate in plates)
        score += total_cuts * 100

        # 3. 그룹화 점수 (같은 크기가 연속이면 좋음)
        for plate in plates:
            score -= self._calculate_grouping_score(plate['pieces']) * 10

        # 4. 공간 사용률 (높을수록 좋음)
        for plate in plates:
            utilization = sum(p['area'] for p in plate['pieces']) / (self.plate_width * self.plate_height)
            score -= utilization * 1000

        return score

    def _calculate_grouping_score(self, pieces):
        """그룹화 점수 계산"""
        from collections import defaultdict

        if not pieces:
            return 0

        # 같은 크기 조각들의 연속성 체크
        groups = defaultdict(list)
        for i, piece in enumerate(pieces):
            groups[piece['original']].append(i)

        score = 0
        for original, indices in groups.items():
            if len(indices) <= 1:
                continue
            # 연속된 조각들에 보너스
            for i in range(len(indices) - 1):
                if indices[i+1] - indices[i] == 1:
                    score += 1  # 연속 보너스

        return score

    def _pack_sequence(self, sequence):
        """시퀀스를 판 배치로 변환"""
        plates = []
        current_plate = {
            'pieces': [],
            'cuts': [],
            'free_spaces': [FreeSpace(0, 0, self.plate_width, self.plate_height)]
        }

        for piece in sequence:
            placement = self._find_placement(current_plate, piece)

            if placement:
                self._place_piece(current_plate, piece, placement)
            else:
                plates.append(current_plate)
                current_plate = {
                    'pieces': [],
                    'cuts': [],
                    'free_spaces': [FreeSpace(0, 0, self.plate_width, self.plate_height)]
                }
                placement = self._find_placement(current_plate, piece)
                if placement:
                    self._place_piece(current_plate, piece, placement)

        if current_plate['pieces']:
            plates.append(current_plate)

        return plates

    def _find_placement(self, plate, piece):
        """AlignedFreeSpacePacker와 동일한 정렬 우선 배치"""
        w, h = piece['width'], piece['height']

        existing_x = set([0])
        existing_y = set([0])
        for p in plate['pieces']:
            existing_x.add(p['x'])
            pw = p.get('placed_w', p['height'] if p.get('rotated') else p['width'])
            ph = p.get('placed_h', p['width'] if p.get('rotated') else p['height'])
            existing_x.add(p['x'] + pw + self.kerf)
            existing_y.add(p['y'])
            existing_y.add(p['y'] + ph + self.kerf)

        candidates = []

        for space in plate['free_spaces']:
            # 일반 방향
            if w + self.kerf <= space.width and h + self.kerf <= space.height:
                x_aligned = 1 if space.x in existing_x else 0
                y_aligned = 1 if space.y in existing_y else 0
                alignment_score = x_aligned + y_aligned
                waste = (space.width - w) * (space.height - h)

                candidates.append({
                    'space': space, 'x': space.x, 'y': space.y,
                    'width': w, 'height': h, 'rotated': False,
                    'alignment_score': alignment_score, 'waste': waste
                })

            # 회전 방향
            if self.allow_rotation and h + self.kerf <= space.width and w + self.kerf <= space.height:
                x_aligned = 1 if space.x in existing_x else 0
                y_aligned = 1 if space.y in existing_y else 0
                alignment_score = x_aligned + y_aligned
                waste = (space.width - h) * (space.height - w)

                candidates.append({
                    'space': space, 'x': space.x, 'y': space.y,
                    'width': h, 'height': w, 'rotated': True,
                    'alignment_score': alignment_score, 'waste': waste
                })

        if not candidates:
            return None

        candidates.sort(key=lambda c: (-c['alignment_score'], c['waste']))
        return candidates[0]

    def _place_piece(self, plate, piece, placement):
        space = placement['space']
        x, y = placement['x'], placement['y']
        w, h = placement['width'], placement['height']

        plate['pieces'].append({
            **piece, 'x': x, 'y': y,
            'rotated': placement['rotated']
        })

        plate['free_spaces'].remove(space)

        if space.width > w + self.kerf:
            plate['free_spaces'].append(FreeSpace(
                x + w + self.kerf, y,
                space.width - w - self.kerf, h + self.kerf
            ))

        if space.height > h + self.kerf:
            plate['free_spaces'].append(FreeSpace(
                x, y + h + self.kerf,
                space.width, space.height - h - self.kerf
            ))

    def _crossover_preserve_groups(self, parent1, parent2):
        """그룹을 보존하는 교배"""
        from collections import defaultdict

        # 부모1의 그룹 구조 분석
        groups1 = defaultdict(list)
        for i, piece in enumerate(parent1):
            groups1[piece['original']].append((i, piece))

        # 부모2에서 그룹 경계 찾기
        groups2 = defaultdict(list)
        for i, piece in enumerate(parent2):
            groups2[piece['original']].append((i, piece))

        # 교차점을 그룹 경계에서 선택
        group_keys = list(groups1.keys())
        if len(group_keys) <= 1:
            return list(parent1)  # 그룹이 1개 이하면 그대로

        # 랜덤 그룹 경계 선택
        cross_group_idx = random.randint(0, len(group_keys) - 1)
        cross_group = group_keys[cross_group_idx]

        # parent1에서 cross_group까지의 조각 수
        cross_point = sum(len(groups1[k]) for k in group_keys[:cross_group_idx+1])

        # 교배
        child = []
        child.extend(parent1[:cross_point])

        # parent2에서 아직 없는 조각들 추가
        used_ids = set(id(p) for p in child)
        for piece in parent2:
            if id(piece) not in used_ids:
                child.append(piece)

        return child

    def _mutate_preserve_groups(self, individual):
        """그룹 내에서만 섞는 변이"""
        from collections import defaultdict

        groups = defaultdict(list)
        for i, piece in enumerate(individual):
            groups[piece['original']].append(i)

        # 랜덤 그룹 선택
        group_keys = list(groups.keys())
        if not group_keys:
            return

        selected_group = random.choice(group_keys)
        indices = groups[selected_group]

        if len(indices) < 2:
            return  # 조각이 1개면 섞을 수 없음

        # 그룹 내에서 2개 위치 교환
        i, j = random.sample(indices, 2)
        individual[i], individual[j] = individual[j], individual[i]

    def _create_grouped_sequence(self, pieces):
        """같은 크기 조각들을 그룹화한 시퀀스 생성"""
        from collections import defaultdict

        groups = defaultdict(list)
        for piece in pieces:
            groups[piece['original']].append(piece)

        sorted_groups = sorted(
            groups.items(),
            key=lambda item: item[1][0]['area'],
            reverse=True
        )

        result = []
        for _, group_pieces in sorted_groups:
            result.extend(group_pieces)

        return result


# ============= 메인 실행 부분 =============

def run_optimization():
    """최적화 실행"""
    pieces = [
        (800, 310, 2),
        (644, 310, 3),
        (371, 270, 4),
        (369, 640, 2),
    ]

    PLATE_WIDTH = 2440
    PLATE_HEIGHT = 1220
    KERF = 5

    print("="*60)
    print("MDF 재단 최적화 - 실제 Guillotine Cut")
    print("="*60)

    # 회전 가능 여부 설정
    rotation_input = input("조각 회전 허용? (y/n, 기본값 y): ").strip().lower() or "y"
    allow_rotation = rotation_input in ("y", "yes", "예", "")

    if allow_rotation:
        print("✓ 회전 허용 (결이 없는 재질)")
    else:
        print("✓ 회전 금지 (결이 있는 재질)")

    print("="*60)
    print("1. 정렬 우선 자유 공간 (그리디)")
    print("2. 유전 알고리즘")
    print("3. Beam Search (백트래킹)")
    print("4. Look-ahead (그룹화 휴리스틱)")
    print("5. 개선된 유전 알고리즘 (추천)")
    print("="*60)

    strategy_choice = input("전략 선택 (1-5, 기본값 5): ").strip() or "5"

    if strategy_choice == "1":
        packer = AlignedFreeSpacePacker(PLATE_WIDTH, PLATE_HEIGHT, KERF, allow_rotation)
        print("\n정렬 우선 자유 공간 전략 선택")
    elif strategy_choice == "2":
        packer = GeneticPacker(PLATE_WIDTH, PLATE_HEIGHT, KERF, allow_rotation)
        print("\n유전 알고리즘 전략 선택")
    elif strategy_choice == "3":
        packer = BeamSearchPacker(PLATE_WIDTH, PLATE_HEIGHT, KERF, allow_rotation, beam_width=3)
        print("\nBeam Search 전략 선택 (beam_width=3)")
    elif strategy_choice == "4":
        packer = LookAheadPacker(PLATE_WIDTH, PLATE_HEIGHT, KERF, allow_rotation)
        print("\nLook-ahead 전략 선택")
    else:  # "5" or default
        packer = ImprovedGeneticPacker(PLATE_WIDTH, PLATE_HEIGHT, KERF, allow_rotation)
        print("\n개선된 유전 알고리즘 전략 선택")

    plates = packer.pack(pieces)

    # 색상
    piece_types = set(f"{w}x{h}" for w, h, _ in pieces)
    colors = {ptype: plt.cm.Set3(i / len(piece_types))
              for i, ptype in enumerate(sorted(piece_types))}

    # 시각화
    fig, axes = plt.subplots(1, len(plates), figsize=(10 * len(plates), 5))
    if len(plates) == 1:
        axes = [axes]

    for plot_idx, plate in enumerate(plates):
        ax = axes[plot_idx]

        print(f"\n{'='*60}")
        print(f"원판 {plot_idx + 1}")
        print(f"배치된 조각: {len(plate['pieces'])}개")
        print(f"절단 횟수: {len(plate['cuts'])}회\n")

        # 절단선 순서 출력
        print("절단 순서:")
        for cut in plate['cuts']:
            direction = "수평" if cut['direction'] == 'H' else "수직"
            print(f"  {cut['order']:2d}. {direction} {cut['position']:4.0f}mm "
                  f"(영역 {cut['region_x']:.0f},{cut['region_y']:.0f} "
                  f"{cut['region_w']:.0f}×{cut['region_h']:.0f})")

        # 조각들의 최종 크기 검증
        print("\n조각 크기 검증 (상세):")
        all_exact = True
        for i, piece in enumerate(plate['pieces']):
            required = f"{piece['width']}×{piece['height']}"

            # 회전 고려
            if piece.get('rotated', False):
                req_w, req_h = piece['height'], piece['width']
            else:
                req_w, req_h = piece['width'], piece['height']

            # placed_w/h가 없으면 아직 트리밍 안됨
            if 'placed_w' not in piece or 'placed_h' not in piece:
                actual = "트리밍 전"
                match = "✗"
                all_exact = False
            else:
                actual = f"{piece['placed_w']}×{piece['placed_h']}"
                match = "✓" if (abs(piece['placed_w'] - req_w) <= 1 and
                               abs(piece['placed_h'] - req_h) <= 1) else "✗"
                if match == "✗":
                    all_exact = False

            pos = f"({piece['x']:.0f},{piece['y']:.0f})"
            print(f"  [{i+1}] {match} 위치: {pos}, 필요: {required}, 실제: {actual}, 기대: {req_w}×{req_h}")

        if all_exact:
            print("\n  ✅ 모든 조각이 정확한 크기입니다")
        else:
            print("\n  ❌ 일부 조각이 부정확합니다")

        ax.add_patch(MPLRect((0, 0), PLATE_WIDTH, PLATE_HEIGHT,
                             fill=False, edgecolor='black', linewidth=2))

        total_area = 0
        for piece in plate['pieces']:
            x, y = piece['x'], piece['y']
            # placed_w/h가 없으면 회전 고려한 크기 사용
            if 'placed_w' in piece and 'placed_h' in piece:
                w, h = piece['placed_w'], piece['placed_h']
            else:
                if piece.get('rotated', False):
                    w, h = piece['height'], piece['width']
                else:
                    w, h = piece['width'], piece['height']
            orig = piece['original']

            piece_type = f"{orig[0]}x{orig[1]}"
            color = colors[piece_type]

            rect_patch = MPLRect((x, y), w, h,
                                linewidth=1, edgecolor='black',
                                facecolor=color, alpha=0.7)
            ax.add_patch(rect_patch)

            cx, cy = x + w/2, y + h/2
            label = f"{w}×{h}"
            if piece['rotated']:
                label += "\n(회전)"
            ax.text(cx, cy, label, ha='center', va='center',
                   fontsize=8, fontweight='bold')

            total_area += w * h

        # 절단선 - 영역 내에서만
        for cut in plate['cuts']:
            if cut['direction'] == 'H':
                ax.plot([cut['start'], cut['end']],
                       [cut['position'], cut['position']],
                       'r-', linewidth=2.5, alpha=0.8)
                mid_x = (cut['start'] + cut['end']) / 2
                ax.text(mid_x, cut['position'], str(cut['order']),
                       ha='center', va='bottom', fontsize=11,
                       fontweight='bold', color='red',
                       bbox=dict(boxstyle='circle,pad=0.3', facecolor='white',
                                edgecolor='red', linewidth=2))
            else:
                ax.plot([cut['position'], cut['position']],
                       [cut['start'], cut['end']],
                       'b-', linewidth=2.5, alpha=0.8)
                mid_y = (cut['start'] + cut['end']) / 2
                ax.text(cut['position'], mid_y, str(cut['order']),
                       ha='left', va='center', fontsize=11,
                       fontweight='bold', color='blue',
                       bbox=dict(boxstyle='circle,pad=0.3', facecolor='white',
                                edgecolor='blue', linewidth=2))

        usage = total_area / (PLATE_WIDTH * PLATE_HEIGHT) * 100
        print(f"\n  사용률: {usage:.1f}%")

        ax.set_xlim(0, PLATE_WIDTH)
        ax.set_ylim(0, PLATE_HEIGHT)
        ax.set_aspect('equal')
        ax.set_xlabel('가로 (mm)')
        ax.set_ylabel('세로 (mm)')
        ax.set_title(f'원판 {plot_idx + 1} (2440×1220)\n사용률: {usage:.1f}% | 절단: {len(plate["cuts"])}회',
                    fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.3)

    print(f"\n{'='*60}")
    print(f"총 사용 원판: {len(plates)}장")
    print(f"총 절단 횟수: {sum(len(p['cuts']) for p in plates)}회")

    legend_elements = [patches.Patch(facecolor=colors[ptype], alpha=0.7,
                                    edgecolor='black', label=ptype)
                      for ptype in sorted(piece_types)]
    fig.legend(handles=legend_elements, loc='upper center',
              bbox_to_anchor=(0.5, 0.98), ncol=len(piece_types))

    plt.tight_layout()
    plt.savefig('mdf_cutting_guillotine.png', dpi=150, bbox_inches='tight')
    print(f"\n시각화 파일 저장: mdf_cutting_guillotine.png")
    plt.show()


def main():
    """CLI 엔트리 포인트"""
    run_optimization()


if __name__ == "__main__":
    main()
