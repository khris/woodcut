"""유전 알고리즘 + AlignedFreeSpace 배치 전략"""

import random
from collections import defaultdict
from ..packing import PackingStrategy, FreeSpace


class GeneticAlignedFreeSpacePacker(PackingStrategy):
    """유전 알고리즘 + AlignedFreeSpace 배치 전략

    배치 시퀀스를 유전 알고리즘으로 최적화하고,
    각 조각의 배치는 AlignedFreeSpace 전략 사용
    """

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
