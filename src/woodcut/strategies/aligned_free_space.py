"""정렬 우선 자유 공간 패킹 전략"""

from ..packing import PackingStrategy, FreeSpace


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
