# 배치-절단 통합 설계

## 문제 분석

**현재 구조 (2단계 분리):**
```
1. 배치 단계 (region_based.py)
   - 길로틴 제약을 고려해서 조각 배치
   - 같은 높이끼리 그룹핑, 수평 배치
   - 결과: pieces 리스트 + placed_h/placed_w

2. 절단 단계 (packing.py FSM)
   - 배치된 조각들만 보고 역추적
   - Phase 1: 높이 경계/trimming
   - Phase 2: 너비 경계/trimming
   - Phase 3: 최종 분리 (실행 안 됨!)
```

**문제점:**
- 배치할 때 이미 알고 있는 정보 (그룹 경계, kerf 간격)를 FSM이 역추적해야 함
- FSM이 재귀 중 조각을 분산시켜서 Phase 3 진입 조건 불충족
- 예: 4개 조각 (0,0), (275,0), (550,0), (825,0) → 3개 절단 필요하지만 생성 안 됨

## 해결책: 배치 시점에 절단 메타데이터 생성

### 방안 1: 배치할 때 "필수 절단선" 리스트 생성

**region_based.py `_place_groups_in_region()` 수정:**

```python
def _place_groups_in_region(self, groups, region):
    placed = []
    required_cuts = []  # NEW: 배치 중 생성된 필수 절단선

    current_x = region['x']
    region_y = region['y']
    max_height = region['max_height']

    for group in groups:
        w, h = group['original_size']
        rotated = group['rotated']
        count = group['count']

        piece_w = h if rotated else w
        piece_h = w if rotated else h

        # 그룹의 첫 조각이 아니면, 이전 그룹과의 경계에 절단선 필요
        if placed and current_x > region['x']:
            # 높이가 다른 그룹 사이 = 수직 경계 separation
            prev_group_h = placed[-1]['height'] if not placed[-1]['rotated'] else placed[-1]['width']
            curr_group_h = h if not rotated else w

            if abs(prev_group_h - curr_group_h) > 1:
                required_cuts.append({
                    'type': 'height_boundary_separation',
                    'direction': 'V',
                    'position': current_x - self.kerf,
                    'priority': 1000  # 최우선
                })

        # 그룹 내 조각들 배치
        group_start_x = current_x
        for i in range(count):
            if current_x + piece_w > region['x'] + region['width']:
                return None

            placed.append({
                'width': w,
                'height': h,
                'x': current_x,
                'y': region_y,
                'rotated': rotated,
                'placed_h': max_height,
                'id': len(placed)
            })

            # 그룹 내 조각 사이 = 수직 분리 필요
            if i < count - 1:
                required_cuts.append({
                    'type': 'piece_separation',
                    'direction': 'V',
                    'position': current_x + piece_w,
                    'priority': 500  # 중간 우선순위
                })

            current_x += piece_w + self.kerf

    return {
        'pieces': placed,
        'required_cuts': required_cuts  # NEW
    }
```

### 방안 2: FSM을 배치 시점으로 통합

**더 근본적인 해결:**

```python
class RegionBasedPacker:
    def _place_and_cut_groups(self, groups, region):
        """배치와 동시에 절단 계획 생성"""

        # 1. 그룹들을 배치하면서 영역 트리 생성
        layout_tree = self._build_layout_tree(groups, region)

        # 2. 레이아웃 트리를 순회하며 절단선 생성
        cuts = self._generate_cuts_from_tree(layout_tree)

        # 3. 조각 리스트 평탄화
        pieces = self._flatten_tree(layout_tree)

        return pieces, cuts

    def _build_layout_tree(self, groups, region):
        """
        배치 트리 구조:
        Region(0, 0, 2440, 1220)
        ├─ HGroup(max_h=371)  # 371×270 4개 + 369×640 2개
        │  ├─ VCut(x=1100)
        │  ├─ Left: Pieces(371×270 × 4)
        │  │   └─ VCut(x=270, x=545, x=820)  # 조각 분리
        │  └─ Right: Pieces(369×640 × 2)
        │      ├─ HTrim(y=369)
        │      └─ VCut(x=1740)  # 조각 분리
        ├─ HGroup(max_h=310)  # 644×310 3개
        │  └─ VCut(x=644, x=1293)
        └─ HGroup(max_h=310)  # 800×310 2개
           └─ VCut(x=800)
        """
        pass
```

## 추천: 방안 1 (점진적 개선)

**이유:**
1. 기존 코드 구조 유지 (region_based.py + packing.py 분리)
2. FSM은 `required_cuts` 힌트를 우선 처리
3. 단계적 구현 가능

**구현 단계:**

### Step 1: region_based.py에 `required_cuts` 추가

```python
# Lines 553-576 수정
for i in range(count):
    # ... 조각 배치 ...

    # 조각 간 분리 절단선 기록
    if i < count - 1:
        region['required_cuts'].append({
            'direction': 'V',
            'position': current_x + piece_w,
            'reason': f'separate piece {len(placed)} and {len(placed)+1}'
        })
```

### Step 2: packing.py FSM에서 `required_cuts` 우선 처리

```python
def _split_region(self, region, cuts, cut_order):
    # Phase 0: 배치 단계에서 지정한 필수 절단선
    if hasattr(region, 'required_cuts') and region.required_cuts:
        cut = region.required_cuts.pop(0)
        self._execute_cut_and_recurse(region, cut, cuts, cut_order)
        return

    # Phase 1-1: Height Boundary Separation
    # ...
```

### Step 3: 검증

```bash
python test_cut_bug.py
# 예상: 10-12개 절단선 (11개 조각 분리)
```

이 방안으로 진행할까요?
