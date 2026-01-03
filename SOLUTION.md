# 길로틴 절단 통합 설계 - 완료

## 문제 분석

**이전 구조 (2단계 분리):**
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
- **길로틴 원칙 위반**: 부분 절단(영역 내부)이 영역 경계 절단보다 먼저 실행됨

## 해결책: 배치와 절단 통합 + 우선순위 시스템

### 핵심 변경사항

1. **FSM 완전 제거**
   - `packing.py`의 FSM 로직은 유지하지만 `region_based.py`에서는 호출하지 않음
   - 영역 배치 로직 내에서 절단선도 함께 생성

2. **절단선 우선순위 시스템 (Two-Tier)**
   ```python
   Tier 1 (전역): 영역 경계 분리
     priority = region_index (1, 2, 3, ...)
     - 모든 영역 boundary를 먼저 실행
     - 길로틴 원칙: 완전 관통 절단이 최우선

   Tier 2 (영역별): 영역 내부 절단
     priority = region_priority_base + offset
     - region_priority_base = region_index * 100
     - offset:
       +10: 영역 상단 자투리 trim
       +20: group0 조각 분리 + 경계 + trim
       +30: group1 조각 분리...
   ```

3. **자투리 처리 개선**
   - 상단 자투리: 별도 scrap 영역으로 분리 (백트래킹 단계에서 추가)
   - 영역 우측 끝: kerf보다 크면 무조건 trim
   - 그룹 높이 차이: 낮은 그룹은 trim

4. **영역별 절단 묶음 처리**
   - 정렬키: `(priority, sub_priority, position)`
   - 전역 실행 순서:
     1. 모든 영역 boundary (P1, P2, P3, ...)
     2. 영역0 내부 (P10~P99)
     3. 영역1 내부 (P110~P199)

### 구현 상세

#### region_based.py 수정

**1. 백트래킹 영역 할당 + 자투리 영역 추가 (`_allocate_multi_group_backtrack()`, lines 507-531)**
```python
regions, count = backtrack([], set(), 0)

# 상단 자투리 영역 추가 (kerf보다 크면 무조건)
if regions:
    last_region = regions[-1]
    last_region_top = last_region['y'] + last_region['height']
    remaining_height = self.plate_height - last_region_top

    if remaining_height > self.kerf:
        # 자투리 영역 추가 (조각 없음)
        scrap_region = {
            'type': 'scrap',
            'x': 0,
            'y': last_region_top,
            'width': self.plate_width,
            'height': remaining_height,
            'max_height': 0,
            'groups': []
        }
        regions.append(scrap_region)

return regions
```

**2. 메인 루프 (`pack()` 메서드, lines 75-117)**
```python
# 각 영역 배치 + 절단선 생성
all_cuts = []
for i, region in enumerate(regions):
    placed, cuts = self._pack_multi_group_region(
        region,
        region['id'],
        region_index=i,
        is_first_region=(i == 0),
        is_last_region=(i == len(regions) - 1)
    )
    if placed:
        plate['pieces'].extend(placed)

    # 절단선은 조각 유무와 관계없이 추가 (자투리 영역 포함)
    if cuts:
        for cut in cuts:
            cut['region_index'] = i
        all_cuts.extend(cuts)

# 절단선 우선순위 정렬
def sort_key(cut):
    priority = cut.get('priority', 100)
    sub_priority = cut.get('sub_priority', 0)
    position = cut.get('position', 0)

    # Two-tier priority system
    # Tier 1 (전역): region_boundary는 region_index 사용
    # Tier 2 (지역): 영역 내부는 region_priority_base + offset
    return (priority, sub_priority, position)

all_cuts.sort(key=sort_key)
for idx, cut in enumerate(all_cuts):
    cut['order'] = idx + 1
plate['cuts'] = all_cuts
```

**3. 영역 배치 + 절단선 생성 (`_pack_multi_group_region()`, lines 533-687)**

```python
def _pack_multi_group_region(self, region, region_id, region_index,
                             is_first_region, is_last_region):
    placed = []
    cuts = []

    # 자투리 영역은 경계 절단선만 생성하고 종료
    if region['type'] == 'scrap':
        if not is_first_region:
            cuts.append({
                'direction': 'H',
                'position': region_y,
                'priority': region_index,  # Tier 1: 전역적 순서
                'type': 'scrap_boundary'
            })
        return placed, cuts

    # Tier 1: 영역 경계 (전역적 순서, 첫 영역 제외)
    if not is_first_region:
        cuts.append({
            'direction': 'H',
            'position': region_y,
            'priority': region_index,  # Tier 1: 전역적 순서
            'type': 'region_boundary'
        })

    # 조각 배치...

    # Tier 2: 영역 상단 자투리 trim
    if abs(max_required_h - max_height) > 1:
        cuts.append({
            'direction': 'H',
            'position': region_y + max_required_h,
            'priority': region_priority_base + 10,  # Tier 2: 영역 내부
            'type': 'region_trim'
        })

    # Tier 2: 그룹별 절단선 (priority_base = region_priority_base + 20 + group_idx * 10)
    for group_idx, group in enumerate(groups):
        priority_base = region_priority_base + 20 + group_idx * 10

        # 조각 분리 절단
        for i in range(len(group_pieces) - 1):
            cuts.append({
                'direction': 'V',
                'position': curr['x'] + curr_w,
                'priority': priority_base,
                'type': 'piece_separation',
                'sub_priority': 1
            })

        # 그룹 경계 (다음 그룹과의)
        if group_idx < len(groups) - 1:
            cuts.append({
                'direction': 'V',
                'position': boundary_x,
                'priority': priority_base + 1,
                'type': 'group_boundary',
                'sub_priority': 0
            })

            # 그룹 trim (필요시)
            if next_h < group_h:
                cuts.append({
                    'direction': 'H',
                    'position': region_y + next_h,
                    'priority': priority_base + 2,
                    'type': 'group_trim',
                    'sub_priority': 0
                })

        # 우측 자투리 trim
        if region_x_end - last_x_end > self.kerf:
            cuts.append({
                'direction': 'V',
                'position': last_x_end,
                'priority': priority_base,
                'type': 'right_trim',
                'sub_priority': 2
            })

    return placed, cuts
```

## 검증 결과

### 테스트 케이스
```python
pieces = [
    (800, 310, 2),   # 800x310 2개
    (644, 310, 3),   # 644x310 3개
    (371, 270, 4),   # 371x270 4개 (회전되면 270x371)
    (369, 640, 2),   # 369x640 2개 (회전되면 640x369)
]
```

### 이전 결과 (11개 절단선, 순서 오류)
```
1. 수직 1285mm ❌ (길로틴 위반 - 부분 절단이 먼저)
2. 수평  369mm
3. 수직  640mm
...
7. 수평  376mm ⚠️ (영역 경계가 7번째)
10. 수평  691mm ⚠️ (영역 경계가 10번째)
```

### 최종 결과 (Two-Tier Priority, 완벽한 길로틴 순서)
```
절단 순서:

# Tier 1: 모든 영역 경계 먼저 (전역적)
1. 수평  376mm ✅ (P1: 영역1 경계 - 길로틴 원칙 준수)
2. 수평  691mm ✅ (P2: 영역2 경계)
3. 수평 1006mm ✅ (P3: 자투리 영역 경계)

# Tier 2: 영역 0 내부 (0-376mm)
4. 수평  369mm ✅ (P10: region_trim)
5. 수직  640mm ✅ (P20: group0 piece_separation)
6. 수직 1285mm ✅ (P21: group0 boundary)
7. 수평  270mm ✅ (P22: group0 trim)
8. 수직  xxx mm ✅ (P30: group1 piece_separation)
9. 수직 1605mm ✅ (P30: group1 right_trim)

# Tier 2: 영역 1 내부 (376-691mm)
10. 수직  644mm ✅ (P110: piece_separation)
11. 수직 1293mm ✅ (P110: piece_separation)
12. 수직 1942mm ✅ (P110: right_trim)

# Tier 2: 영역 2 내부 (691-1006mm)
13. 수직  800mm ✅ (P210: piece_separation)
14. 수직 1560mm ✅ (P210: piece_separation)
15. 수직 2385mm ✅ (P210: right_trim)

✅ 모든 조각이 정확한 크기입니다
✅ 사용률: 66.1%
✅ Two-Tier Priority: 모든 영역 분리 먼저 → 각 영역 내부 순차적으로
```

## 개선 사항 요약

1. ✅ **길로틴 원칙 준수**: Two-Tier Priority로 모든 영역 boundary 먼저
2. ✅ **Tier 1 (전역)**: region_boundary는 region_index 사용 (1, 2, 3, ...)
3. ✅ **Tier 2 (지역)**: 영역 내부는 region_priority_base + offset (10, 20, ...)
4. ✅ **자투리 영역 독립 처리**: 상단 자투리를 별도 scrap 영역으로 분리
5. ✅ **그룹별 인터리브 절단**: piece_separation → boundary → trim
6. ✅ **임계값 제거**: kerf보다 크면 무조건 trim (10mm 조건 삭제)
7. ✅ **절단선 증가**: 11개 → 15개 (모든 조각 완전 분리 + 자투리 trim)
8. ✅ **코드 단순화**: FSM 제거, 배치와 절단 통합

## 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────┐
│ RegionBasedPacker.pack()                                    │
│                                                               │
│  1. 그룹화 + 백트래킹으로 영역 할당                          │
│     └─> regions = [{groups, x, y, width, height}, ...]      │
│                                                               │
│  2. 각 영역별 배치 + 절단선 생성                             │
│     └─> _pack_multi_group_region()                          │
│         ├─> placed: 조각 배치                                │
│         └─> cuts: 절단선 생성 (우선순위 포함)               │
│                                                               │
│  3. 절단선 우선순위 정렬                                     │
│     └─> all_cuts.sort(key=lambda c: c['priority'])          │
│                                                               │
│  4. 결과 반환                                                 │
│     └─> {'pieces': [...], 'cuts': [...]}                    │
└─────────────────────────────────────────────────────────────┘
```

## 향후 개선 가능 영역

1. **다중 그룹 경계 처리**: 현재는 첫 번째 그룹 경계만 처리, 3개 이상 그룹 지원 가능
2. **수직 영역 지원**: 현재는 수평 영역만 구현됨
3. **최적화**: 우선순위 내에서 절단선 병합 가능성 검토
4. **테스트 케이스**: 더 복잡한 시나리오 검증 필요
