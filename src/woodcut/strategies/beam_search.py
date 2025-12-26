"""
Beam Search 전략 - 상위 k개 배치 후보 유지하며 최적 경로 탐색
"""

import copy
import random
from ..packing import PackingStrategy, FreeSpace


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
