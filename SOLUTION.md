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

2. **절단선 우선순위 시스템**
   ```python
   priority 1: 영역 경계 (수평 절단 - 길로틴 원칙 준수)
   priority 2: 영역 상단 자투리 trim
   priority 3: 그룹 경계 (수직 절단)
   priority 4: 그룹별 개별 trim
   priority 5: 조각 분리 절단
   priority 6: 우측 자투리 trim
   ```

3. **자투리 처리 추가**
   - 영역 우측 끝: 10mm 이상 남으면 trim
   - 그룹 높이 차이: 낮은 그룹은 trim

### 구현 상세

#### region_based.py 수정

**1. 메인 루프 (`pack()` 메서드, lines 75-97)**
```python
# 각 영역 배치 + 절단선 생성
all_cuts = []
for i, region in enumerate(regions):
    placed, cuts = self._pack_multi_group_region(
        region,
        region['id'],
        is_first_region=(i == 0)
    )
    if placed:
        plate['pieces'].extend(placed)
        all_cuts.extend(cuts)

# 절단선 우선순위 정렬 및 order 부여
all_cuts.sort(key=lambda c: (c.get('priority', 100), c.get('position', 0)))
for idx, cut in enumerate(all_cuts):
    cut['order'] = idx + 1
plate['cuts'] = all_cuts
```

**2. 영역 배치 + 절단선 생성 (`_pack_multi_group_region()`, lines 512-695)**

```python
def _pack_multi_group_region(self, region, region_id, is_first_region):
    placed = []
    cuts = []

    # 우선순위 1: 영역 경계 (첫 영역 제외)
    if not is_first_region:
        cuts.append({
            'direction': 'H',
            'position': region_y,
            'priority': 1,
            'type': 'region_boundary'
        })

    # 조각 배치...

    # 우선순위 2: 영역 상단 자투리 trim
    if abs(max_required_h - max_height) > 1:
        cuts.append({
            'direction': 'H',
            'position': region_y + max_required_h,
            'priority': 2,
            'type': 'region_trim'
        })

    # 우선순위 3: 그룹 경계 절단
    if abs(curr_h - next_h) > 1:
        cuts.append({
            'direction': 'V',
            'position': boundary_x,
            'priority': 3,
            'type': 'group_boundary'
        })

    # 우선순위 4: 그룹별 trim
    if abs(left_h - max_required_h) > 1:
        cuts.append({
            'direction': 'H',
            'position': region_y + left_h,
            'priority': 4,
            'type': 'group_trim'
        })

    # 우선순위 5: 조각 분리
    for i in range(len(sorted_pieces) - 1):
        if i != group_boundary_idx:
            cuts.append({
                'direction': 'V',
                'position': curr['x'] + curr_w,
                'priority': 5,
                'type': 'piece_separation'
            })

    # 우선순위 6: 우측 자투리 trim
    if region_x_end - last_x_end > self.kerf + 10:
        cuts.append({
            'direction': 'V',
            'position': last_x_end,
            'priority': 6,
            'type': 'right_trim'
        })

    return placed, cuts
```

**3. 폴백 제거 (line 58-66)**
```python
if not regions:
    print("\n⚠️  백트래킹 실패 - 배치 불가능한 조각들")
    break
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

### 현재 결과 (14개 절단선, 올바른 순서)
```
절단 순서:
1. 수평  376mm ✅ (영역 경계 - 길로틴 원칙 준수)
2. 수평  691mm ✅ (영역 경계 - 길로틴 원칙 준수)
3. 수직 1285mm ✅ (그룹 경계)
4. 수평  369mm ✅ (좌측 그룹 trim)
5. 수직  640mm ✅ (조각 분리)
6. 수직  644mm ✅ (조각 분리)
7. 수직  800mm ✅ (조각 분리)
8. 수직 1293mm ✅ (조각 분리)
9. 수직 1560mm ✅ (조각 분리)
10. 수직 1835mm ✅ (조각 분리)
11. 수직 2110mm ✅ (조각 분리)
12. 수직 1605mm ✅ (우측 자투리 trim)
13. 수직 1942mm ✅ (우측 자투리 trim)
14. 수직 2385mm ✅ (우측 자투리 trim)

✅ 모든 조각이 정확한 크기입니다
✅ 사용률: 66.1%
```

## 개선 사항 요약

1. ✅ **길로틴 원칙 준수**: 영역 경계 절단이 최우선 실행
2. ✅ **자투리 처리**: 우측 끝 자투리 trim 추가 (3개)
3. ✅ **절단선 증가**: 11개 → 14개 (모든 조각 완전 분리)
4. ✅ **코드 단순화**: FSM 제거, 배치와 절단 통합
5. ✅ **폴백 제거**: 명확한 실패 처리

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
