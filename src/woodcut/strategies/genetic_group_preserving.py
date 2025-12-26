"""
그룹 보존 유전 알고리즘 전략 - 같은 크기 조각들의 그룹을 보존하며 교배 및 변이
"""

import random
from collections import defaultdict
from ..packing import PackingStrategy, FreeSpace


class GeneticGroupPreservingPacker(PackingStrategy):
    """전략 5: 그룹 보존 유전 알고리즘 - 그룹 보존 연산자 + Beam Search 초기화"""

    def __init__(self, plate_width, plate_height, kerf=5, allow_rotation=True):
        super().__init__(plate_width, plate_height, kerf, allow_rotation)

    def pack(self, pieces):
        all_pieces = self.expand_pieces(pieces)

        population_size = 30  # 증가
        generations = 100  # 증가

        print(f"\n그룹 보존 유전 알고리즘: 세대 {generations}개, 개체 {population_size}개")

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
