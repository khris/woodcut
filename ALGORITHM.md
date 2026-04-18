# Woodcut 알고리즘 상세

> 현재 코드 기준 문서 (`src/woodcut/strategies/region_based.py`, `src/woodcut/packing.py`)

---

## 전체 데이터 흐름

```
입력: [(width, height, count), ...]
        ↓
expand_pieces()          → 개별 조각 dict 확장
        ↓
_group_by_exact_size()   → 정확한 크기별 그룹화
        ↓
_generate_group_options() → 회전/비회전 옵션 생성
        ↓
_flatten_group_options()  → 가로/세로 배치 변형 평면화
        ↓
_allocate_anchor_backtrack() → 앵커 기반 백트래킹
        ↓
_optimize_trim_placement()   → trim 공간 재활용 최적화
        ↓
_pack_multi_group_region() × N → 조각 배치 + 절단선 생성
        ↓
sort_key 정렬             → 절단 우선순위 확정
        ↓
출력: plates[{'pieces': [...], 'cuts': [...]}]
```

---

## 1단계: 그룹화 및 변형 생성

### 1-1. 정확한 크기별 그룹화 (`_group_by_exact_size`)

동일한 `(width, height)` 쌍끼리만 그룹화합니다. 유사 크기 병합은 지원하지 않습니다.

```python
groups = [
    {'size': (800, 310), 'count': 2, 'total_area': 496000},
    {'size': (644, 310), 'count': 3, 'total_area': 598920},
    ...
]
# total_area 내림차순 정렬 (큰 그룹 우선)
```

### 1-2. 회전 옵션 생성 (`_generate_group_options`)

각 그룹에 대해 회전/비회전 옵션을 생성합니다. `allow_rotation=False`이면 비회전만.

```python
# (369, 640) 조각의 경우
options = [
    {'rotated': False, 'height': 640, 'width': 369},
    {'rotated': True,  'height': 369, 'width': 640},  # allow_rotation=True 시
]
```

### 1-3. 배치 변형 평면화 (`_flatten_group_options`)

각 회전 옵션에 대해 **가로 배치**(기본)와 **세로 배치**(stacked) 변형을 생성합니다.
세로 배치는 가로 배치 시 판 너비를 초과하는 경우에만 생성됩니다.

```python
# 가로 배치 (기본)
{
    'original_size': (369, 640),
    'count': 2,
    'rotated': False,
    'stacked': False,
    'height': 640,           # 조각 하나의 높이
    'width': 369,            # 조각 하나의 너비
    'total_width': 369 + kerf + 369 + kerf  # count × (width + kerf)
}

# 세로 배치 (가로 배치가 판 너비 초과 시)
{
    'stacked': True,
    'height': (640 + kerf) * 2,  # count × (height + kerf)
    'total_width': 369 + kerf    # 한 조각 너비만
}
```

---

## 2단계: 앵커 기반 백트래킹 (`_allocate_anchor_backtrack`)

### 핵심 아이디어

높이가 가장 큰 그룹을 **앵커**로 선택하고, 앵커 높이 이하인 호환 그룹을 수평으로 채웁니다.
각 영역마다 이 과정을 반복하며, 최대 조각 수를 배치하는 조합을 탐색합니다.

### 앵커 선택 전략

```python
# 높이 내림차순으로 앵커 후보 나열
# 같은 original_size의 다른 회전 옵션도 후보로 포함
anchor_candidates = sorted(unused_variants, key=lambda x: x['height'], reverse=True)
```

높이가 클수록 더 많은 호환 그룹을 수용할 수 있습니다.

### 호환 그룹 탐색 (`_build_region_with_anchor`)

앵커가 결정되면 다음 조건을 만족하는 그룹을 탐욕적으로 추가합니다:

1. **높이 제약**: `v['height'] <= anchor['height']`
2. **너비 제약**: `current_width + kerf + v['total_width'] <= plate_width`
3. **중복 방지**: 같은 `original_size`는 한 번만 (회전 포함)

```python
# 정렬: 앵커와 높이 유사도 우선 → 면적 큰 그룹 우선
compatible.sort(key=lambda v: (abs(max_height - v['height']), -v['area']))
```

### 백트래킹 재귀 구조

```python
def backtrack(used_groups, y_offset):
    if len(used_groups) == total_groups:
        return [], 0  # 모든 그룹 배치 완료

    for anchor in anchor_candidates:
        # 판 높이/너비 초과 시 skip
        if y_offset + anchor['height'] + kerf > plate_height:
            continue

        region_groups, region_used = _build_region_with_anchor(anchor, ...)
        region = {'y': y_offset, 'height': anchor['height'] + kerf, ...}

        sub_regions, sub_count = backtrack(new_used, new_y)
        total = current_count + sub_count

        if total > best_count:
            best_count, best_regions = total, [region] + sub_regions

    return best_regions, best_count
```

### 자투리 영역

백트래킹 완료 후, 마지막 영역 상단에 남은 공간이 `kerf`보다 크면 `scrap` 타입 영역으로 추가합니다.

---

## 3단계: Trim 최적화 (`_optimize_trim_placement`)

### 목적

백트래킹으로 배치된 영역에서, 조각과 영역 상단 사이의 **trim 공간**에 이후 영역의 소형 그룹을 이동시킵니다.

### 조건

```python
trim_height = row_height - piece_h - 2 * kerf  # 실제 사용 가능 높이

# skip 조건:
# 1. trim_height < kerf (kerf보다 작은 공간에는 어떤 조각도 배치 불가)
# 2. 같은 행에 piece_h < G < row_height - kerf 인 중간 높이 그룹 존재
#    (해당 그룹의 H컷이 trim 공간을 관통하게 됨)
```

### 동작

이후 영역에서 `lpiece_h <= trim_height`를 만족하는 그룹을 찾아 `trim_rows`로 이동합니다.
이동 후 빈 영역은 `scrap`으로 전환하고, 연속된 `scrap` 영역은 병합합니다.

---

## 4단계: 영역별 배치 및 절단선 생성 (`_pack_multi_group_region`)

### 조각 배치

각 영역의 행(`rows`)을 순회하며 조각을 배치합니다.

**가로 배치 (stacked=False)**:
```python
for _ in range(count):
    placed.append({'x': current_x, 'y': current_y + y_offset, ...})
    current_x += piece_w + kerf
```

**세로 배치 (stacked=True)**:
```python
for i in range(count):
    piece_y = current_y + i * (piece_h + kerf)
    placed.append({'x': current_x, 'y': piece_y, ...})
current_x += piece_w + kerf
```

**trim_rows 조각** (trim 최적화로 이동된 조각들):
```python
trim_y = current_y + trim_row['y_offset']  # piece_h + kerf
```

### 절단선 생성 우선순위

```
priority 1                     : 영역 경계 (region_boundary / scrap_boundary)
priority region_priority_base + 5  : 행(tier) 경계
priority region_priority_base + 10 : 영역 상단 자투리 trim (region_trim)
priority region_priority_base + 20 : 세로 배치(stacked) V trim + H 분리
priority region_priority_base + 20 + group_idx * 10 :
    - 조각 간 분리 (piece_separation, sub_priority=1)
    - 행 끝 우측 trim (right_trim, sub_priority=2)
    - 그룹 경계 (group_boundary)
    - 다음 그룹 높이 trim (group_trim)
priority region_priority_base + 23 : 2차 행 trim (secondary_row_trim)
```

`region_priority_base = region_index * 100`이므로 영역 0, 1, 2... 순서가 자연히 보장됩니다.

### 절단선 정렬 키

```python
def sort_key(cut):
    if cut['priority'] == 1:        # 영역 경계: 전역 위치 순
        return (1, cut['position'], 0, 0)
    else:                           # 영역 내부: 영역 → 그룹 → 위치 순
        return (cut['priority'], cut['region_index'], cut['sub_priority'], cut['position'])
```

**결과**: 모든 영역 경계(priority 1)가 먼저, 그 다음 영역 0 내부 → 영역 1 내부... 순으로 실행됩니다.

---

## 동작 예시 (표준 11개 조각 테스트)

### 입력

```python
pieces = [
    (800, 310, 2),
    (644, 310, 3),
    (371, 270, 4),
    (369, 640, 2),
]
plate = 2440 × 1220mm, kerf = 5mm
```

### 백트래킹 결과 (회전 허용)

| 영역 | y 위치 | 높이 | 그룹 구성 |
|------|--------|------|-----------|
| R1   | 0      | 374  | 640×369 (2개) + 270×371 (4개) |
| R2   | 374    | 315  | 644×310 (3개) |
| R3   | 689    | 315  | 800×310 (2개) |
| scrap| 1004   | 216  | 자투리 |

### 절단 순서 구조

```
[Priority 1] 영역 경계 (위→아래):
  H @ y=374  (R1→R2 경계)
  H @ y=689  (R2→R3 경계)
  H @ y=1004 (R3→자투리 경계)

[R1 내부, priority 100+]:
  V @ x=1285  (그룹 경계: 640×369 | 270×371)
  H @ y=369   (우측 그룹 trim, group_trim)
  V @ x=640   (조각 분리, 640×369 그룹)
  V @ x=1285  (조각 분리, 640×369 그룹)
  V @ x=1605  (우측 자투리 trim, right_trim)
  ...

[R2 내부, priority 200+]:
  V @ x=644   (조각 분리)
  V @ x=1293  (조각 분리)
  V @ x=1942  (우측 자투리 trim)
  ...
```

---

## 폴백 전략

백트래킹이 실패하면 (`regions == []`) AlignedFreeSpace 방식을 사용합니다.

```python
plate = {'free_spaces': [FreeSpace(0, 0, plate_w, plate_h)]}
for piece in remaining_pieces:
    placement = _find_best_placement_simple(free_spaces, placed, piece)
    if placement:
        _apply_placement(free_spaces, placed, piece, placement)
generate_guillotine_cuts(plate)  # packing.py의 FSM 절단 알고리즘 사용
```

---

## FSM 절단 알고리즘 (`_split_region`, packing.py)

폴백 경로에서 `generate_guillotine_cuts()`가 호출할 때 사용되는 재귀 FSM입니다.
5개 Phase를 순서대로 시도하며, 조건이 맞는 첫 번째 절단선을 실행하고 재귀합니다.

```
Phase 0  : required_cuts 우선 실행 (배치 단계 힌트)
Phase 1-1: Height Boundary Separation (required_h가 다른 경계 → V cut)
Phase 1-2: Height Trimming (placed_h != required_h → H 또는 V cut)
Phase 2-1: Width Boundary Separation (required_w가 다른 경계 → H cut)
Phase 2-2: Width Trimming (placed_w != required_w → V 또는 H cut)
Phase 3  : Final Separation (조각 경계 kerf 위치 → V/H cut)
DONE     : 조각 1개이고 placed_w/h가 정확
```

각 Phase에서 절단 실행 시 (`_execute_cut_and_recurse`):
1. 절단선을 `cuts`에 추가
2. Trimming cut이면 관련 조각의 `placed_w` 또는 `placed_h` 업데이트
3. 영역을 두 서브영역으로 분리하고 각각 재귀 호출

---

## 핵심 데이터 구조

### 조각 (piece)

```python
{
    'width': 800,        # 원본 너비
    'height': 310,       # 원본 높이
    'x': 0,              # 배치 x 좌표 (글로벌)
    'y': 0,              # 배치 y 좌표 (글로벌)
    'rotated': False,    # 회전 여부
    'placed_w': 800,     # 실제 너비 (트림 후, _pack_multi_group_region 말미에 설정)
    'placed_h': 310,     # 실제 높이
    'id': 0,
    'original': (800, 310)
}
```

### 영역 (region)

```python
{
    'type': 'horizontal',  # 'horizontal' | 'scrap'
    'id': 'R1',
    'x': 0, 'y': 0,
    'width': 2440, 'height': 374,
    'max_height': 369,     # 가장 높은 그룹의 높이 (kerf 제외)
    'rows': [
        {
            'height': 374,
            'groups': [
                {
                    'original_size': (369, 640),
                    'rotated': False,
                    'count': 2,
                    'stacked': False,
                    'trim_rows': [...]  # trim 최적화 결과
                },
                ...
            ]
        }
    ]
}
```

### 절단선 (cut)

```python
{
    'direction': 'H',      # 'H' (수평) | 'V' (수직)
    'position': 374,       # 절단 위치 (y 또는 x 좌표)
    'start': 0,            # 절단선 시작 (반대 축)
    'end': 2440,           # 절단선 끝
    'priority': 1,         # 정렬 우선순위
    'sub_priority': 0,
    'region_index': 0,
    'type': 'region_boundary',
    'order': 1             # 최종 실행 순서 (정렬 후 부여)
}
```

---

## 참고

- `src/woodcut/strategies/region_based.py` — 메인 패킹 알고리즘
- `src/woodcut/packing.py` — 베이스 클래스 + FSM 절단 알고리즘 (폴백 경로)
- `src/woodcut/visualizer.py` — 배치 및 절단선 시각화
- `.solution/003-20260110-verification-checklist.md` — 검증 체크리스트
