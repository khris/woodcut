# Woodcut 알고리즘 상세

> PLAN.md의 간략한 개요와 달리, 이 문서는 RegionBasedPacker의 상세 구현을 설명합니다.

---

## 핵심 알고리즘 상세

### 1. 다중 그룹 영역 배치

```python
def pack(self, pieces):
    while remaining_pieces:
        # 1. 레벨 1: 정확히 같은 크기끼리 그룹화
        groups = self._group_by_exact_size(remaining_pieces)

        # 2. 각 그룹의 회전 옵션 생성
        group_options = self._generate_group_options(groups)

        # 3. 그룹 회전 옵션 평면화
        all_variants = self._flatten_group_options(group_options)

        # 4. 백트래킹으로 최적 조합 찾기
        regions = self._allocate_multi_group_backtrack(group_sets)

        # 5. 각 영역 내 배치 + 절단선 생성 (통합)
        all_cuts = []
        for i, region in enumerate(regions):
            placed, cuts = self._pack_multi_group_region(
                region, region_index=i, is_first_region=(i==0)
            )
            if placed:
                plate['pieces'].extend(placed)
            if cuts:
                for cut in cuts:
                    cut['region_index'] = i
                all_cuts.extend(cuts)

        # 6. 절단선 우선순위 정렬
        all_cuts.sort(key=sort_key)  # (priority, region_index, sub_priority, position)
        plate['cuts'] = all_cuts

        # 7. 배치된 조각 제거, 다음 판으로
        remaining_pieces = [...]
```

**참조**: `src/woodcut/strategies/region_based.py`의 `pack()` 메서드

---

### 2. 호환 그룹 세트 생성

```python
# 예시: 644×310 (3개) + 640×369 (2개, 회전)
{
    'type': 'horizontal',
    'max_height': 374,  # max(310, 369) + kerf
    'groups': [
        {'original_size': (644, 310), 'rotated': False, 'count': 3},
        {'original_size': (369, 640), 'rotated': True, 'count': 2}
    ],
    'total_area': 598920 + 472320
}
```

**주의**: 현재는 정확히 같은 크기끼리만 그룹화됩니다. 유사 크기 병합 기능은 향후 개선 예정입니다.

**참조**: `src/woodcut/strategies/region_based.py`의 `_flatten_group_options()` 메서드

---

### 3. 백트래킹 영역 할당

```python
def backtrack(selected_sets, used_groups, y_offset):
    # 종료 조건: 모든 그룹 배치 완료
    if len(used_groups) == total_groups:
        return selected_sets, placed_count

    # 각 세트 시도
    for group_set in group_sets:
        # 1. 이미 사용된 그룹은 스킵
        if set_groups & used_groups:
            continue

        # 2. 공간 체크
        if y_offset + region_height > plate_height:
            continue

        # 3. 재귀 호출
        result_sets, result_count = backtrack(
            selected_sets + [region],
            used_groups | set_groups,
            y_offset + region_height
        )

        if result_count > best_count:
            best_count = result_count
            best_sets = result_sets

    return best_sets, best_count
```

**최적화:**
- 영역 세트를 면적순으로 정렬 (큰 세트 우선)
- 공간 부족 시 조기 가지치기
- 모든 그룹 배치 시 즉시 종료

**참조**: `src/woodcut/strategies/region_based.py`의 `_allocate_multi_group_backtrack()` 메서드

---

### 4. 절단선 생성 알고리즘 (통합형 배치+절단)

#### 영역별 절단선 생성 로직

```python
def _pack_multi_group_region(self, region, region_id, region_index,
                             is_first_region, is_last_region):
    cuts = []

    # 자투리 영역 처리
    if region['type'] == 'scrap':
        if not is_first_region:
            cuts.append({'priority': 1, 'type': 'scrap_boundary', ...})
        return placed, cuts

    # Priority 1: 영역 경계 (첫 영역 제외)
    if not is_first_region:
        cuts.append({'priority': 1, 'type': 'region_boundary', ...})

    # Priority 2: 영역 상단 자투리 trim
    if abs(max_required_h - max_height) > 1:
        cuts.append({'priority': 2, 'type': 'region_trim', ...})

    # Priority 3: 그룹 경계 절단
    if abs(curr_h - next_h) > 1:
        cuts.append({'priority': 3, 'type': 'group_boundary', ...})

    # Priority 4: 그룹별 개별 trim
    if abs(left_h - max_required_h) > 1:
        cuts.append({'priority': 4, 'type': 'group_trim', ...})

    # Priority 5: 조각 분리 + 우측 자투리 (sub_priority로 구분)
    for i in range(len(sorted_pieces) - 1):
        if i != group_boundary_idx:
            cuts.append({'priority': 5, 'sub_priority': 1,
                        'type': 'piece_separation', ...})

    if region_x_end - last_x_end > self.kerf:
        cuts.append({'priority': 5, 'sub_priority': 2,
                    'type': 'right_trim', ...})

    return placed, cuts
```

**참조**: `src/woodcut/strategies/region_based.py`의 `_pack_multi_group_region()` 메서드

---

#### 우선순위 정렬 및 길로틴 순서 보장

```python
def sort_key(cut):
    priority = cut.get('priority', 100)
    region_idx = cut.get('region_index', 0)
    sub_priority = cut.get('sub_priority', 0)
    position = cut.get('position', 0)

    if priority == 1:
        # 영역 경계: position만 고려 (위→아래 순)
        return (priority, position, 0, 0)
    else:
        # 영역 내부: region_index → sub_priority → position
        # 한 영역 완료 후 다음 영역
        return (priority, region_idx, sub_priority, position)
```

**결과:**
- 영역 경계(priority 1) 모두 먼저 실행 → 길로틴 원칙 준수
- 각 영역별로 절단 완료 후 다음 영역 진행
- 조각 분리와 우측 trim이 같은 영역 내에서 혼합 실행

---

## 알고리즘 동작 예시 (11개 조각)

### 입력

```python
pieces = [
    (800, 310, 2),   # 800×310mm 2개
    (644, 310, 3),   # 644×310mm 3개
    (371, 270, 4),   # 371×270mm 4개
    (369, 640, 2),   # 369×640mm 2개 (회전 가능)
]
```

### 백트래킹 결과

- **영역 0**: 640×369 (2개, 회전) + 270×371 (4개, 회전)
- **영역 1**: 644×310 (3개)
- **영역 2**: 800×310 (2개)
- **영역 3 (scrap)**: 상단 자투리 (214mm)

### 절단 순서 (15개)

```
Tier 1 - Priority 1 (영역 경계):
1. 수평  376mm  (영역0→영역1 경계)
2. 수평  691mm  (영역1→영역2 경계)
3. 수평 1006mm  (영역2→자투리 경계)

Tier 2 - 영역0 처리 (Priority 2-5, region_index=0):
4. 수직 1285mm  (그룹 경계: 640×369 | 270×371)
5. 수평  369mm  (좌측 그룹 trim)
6. 수직  640mm  (조각 분리)
7. 수직 1285mm  (조각 분리)
8. 수직 1605mm  (우측 자투리 trim)

Tier 2 - 영역1 처리 (Priority 2-5, region_index=1):
9. 수직  644mm  (조각 분리)
10. 수직 1293mm  (조각 분리)
11. 수직 1942mm  (우측 자투리 trim)

Tier 2 - 영역2 처리 (Priority 2-5, region_index=2):
12. 수직  800mm  (조각 분리)
13. 수직 1560mm  (조각 분리)
14. 수직 1835mm  (조각 분리)
15. 수직 2385mm  (우측 자투리 trim)
```

### 핵심 특징

- ✅ **길로틴 원칙 준수**: 영역 경계(1-3번)가 최우선 실행
- ✅ **영역별 완료**: 영역0 → 영역1 → 영역2 순차 처리
- ✅ **자투리 처리**: 상단 자투리 영역 + 각 영역 우측 trim
- ✅ **조각 분리와 trim 혼합**: 같은 priority 5 내에서 sub_priority로 구분

---

## Two-Tier Priority System 상세

### 문제점 (이전 방식)

```
첫 영역은 boundary 없음 → 내부를 먼저 자름
→ 다음 영역 boundary를 나중에 자름
→ 길로틴 원칙 위반!
```

### 해결 (Two-Tier)

```python
# Tier 1 (전역): 영역 경계 분리
priority = region_index (1, 2, 3, ...)

# Tier 2 (지역): 영역 내부 절단
priority = region_priority_base + offset
  - region_priority_base = region_index * 100
  - offset:
      +10: 영역 상단 자투리 trim (수평)
      +20: group0 조각 분리 + 경계 + trim
      +21: group0 boundary
      +22: group0 trim
      +30: group1 조각 분리...
```

### 정렬 키

```python
(priority, sub_priority, position)
```

### 실행 순서

```
P1, P2, P3 (모든 영역 boundaries)
→ P10, P20, P21, ... (영역0 내부)
→ P110, P120, P121, ... (영역1 내부)
→ P210, P220, P221, ... (영역2 내부)
```

**결과**: 완벽한 길로틴 순서 보장

---

## 코딩 스타일 (Python 3.10+)

### 타입 힌트

```python
def pack(self, pieces: list[tuple[int, int, int]]) -> list[dict]:
    ...
```

### match-case

```python
match cut['type']:
    case 'horizontal':
        process_horizontal(cut)
    case 'vertical':
        process_vertical(cut)
```

### walrus 연산자

```python
if (req_h := piece.get('height')) > max_height:
    ...
```

---

## 다단 배치 (Multi-Tier, 선택적)

**현재 상태**: 계획 단계

옵션 활성화 시 남은 공간에 추가 행을 배치하여 공간 활용률을 향상시키는 기능입니다.

**핵심 개념:**
- 같은 높이 → 같은 영역 (최우선)
- 남은 공간 > threshold → 추가 행 배치 (보수적)
- 각 행은 독립적인 수평 절단선으로 분리 (Guillotine 준수)

**상세**: [.solution/002-20260104-multi-tier-placement.md](../.solution/002-20260104-multi-tier-placement.md)

---

## 참고

상세 구현은 다음 파일 참조:
- `src/woodcut/strategies/region_based.py` - 메인 알고리즘
- `src/woodcut/packing.py` - Guillotine Cut FSM (현재 미사용)
- `src/woodcut/visualizer.py` - 시각화

솔루션 문서:
- [001: Guillotine 절단 통합](../.solution/001-20251231-guillotine-cutting-integration.md)
- [002: 다단 배치](../.solution/002-20260104-multi-tier-placement.md)
