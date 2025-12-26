"""
Look-ahead 휴리스틱 전략 - 그룹화를 방해하는 배치에 페널티 적용
"""

from collections import defaultdict
from ..packing import PackingStrategy, FreeSpace


class LookAheadPacker(PackingStrategy):
    """전략 4: Look-ahead 휴리스틱 - 그룹화를 방해하는 배치에 페널티"""

    def pack(self, pieces):
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
