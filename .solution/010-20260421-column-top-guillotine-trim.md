# 짧은 컬럼 상단 Guillotine trim 누락 — 수정

- **작성일**: 2026-04-21
- **작성자**: Hong Segi + Claude
- **상태**: 승인됨
- **관련 스펙**: [009-secondary-row-trim-bounds](009-20260421-secondary-row-trim-bounds.md) (009 보완)

## 1. 배경

009로 `secondary_row_trim` 범위를 그룹 x 범위로 한정해 "100×764 조각을 가로지르던 H 컷"은 해소됨. 그러나 재현 케이스(2440×1220 × 2 / 2000×280 ×4 + 100×764 ×2 + 760×260 ×14) Sheet 1에 남은 Guillotine 위반이 추가 발견.

### 증상

```
#1 H 1145 [0~2440] scrap_boundary        ← plate 전체 관통
#2 V 2000 [0~1135] right_trim            ← 아래 서브영역 좌/우 분할
#3 H  565 [0~2000] secondary_row_trim    ← 왼쪽 서브영역 관통 OK
#4 H  850 [0~2000] secondary_row_trim    ← OK
#5 H  280 [0~2000] stacked_separation    ← OK
#6 V 2105 [0~ 764] piece_separation      ← 오른쪽 서브영역(440×1135) 부분 관통 ✗
#7 V 2210 [0~ 764] right_trim            ← 부분 관통 ✗
```

오른쪽 서브영역(x=2000~2440, y=0~1135)에 100×764 조각(y=0~764)만 배치되고 **위쪽 빈 공간(y=764~1135)을 분리하는 H 컷이 없음**. 그 결과 V#6·#7이 y=0~764만 부분 관통 → Guillotine 위반.

### 원인

[region_based.py](../src/woodcut/strategies/region_based.py) 안의 기존 trim 경로가 이 케이스를 놓침:

- `region_trim` (line 917): `max_height - max_height_in_region > kerf` 조건만 — stacked 컬럼이 영역 전체 높이를 채우면 발동 안 함.
- `secondary_row_trim` (line 942): `g['y'] > region_y` 조건이라 **2차 행 그룹만** 대상 — 첫째 행은 스킵.
- `group_trim` (line 1088): 그룹 순회 중 **수평 인접** 그룹 사이 높이 차만 봄 — stacked 그룹은 `stacked_group_indices`로 skip되어 오른쪽 이웃을 처리 못 함.

첫째 행에 **최대 높이 컬럼**(stacked)과 **낮은 컬럼**(가로 그룹)이 공존할 때의 상단 trim이 사각지대.

## 2. 설계 결정

### 핵심: "컬럼 top trim" 로직 추가

`_pack_multi_group_region` 안에 **x-컬럼 단위**로 "각 x 범위의 실제 y 천장"을 집계하고, `region_top`보다 낮으면 H 컷을 emit.

```python
# 각 (x_start, x_end) 컬럼의 최대 y 천장
column_top: dict[tuple, int] = {}
for g in groups:
    xs = min(p['x'] for p in g['pieces'])
    xe = max(p['x'] + piece_w(p) for p in g['pieces'])
    column_top[(xs, xe)] = max(column_top.get((xs, xe), 0), g['y'] + g['height'])

region_top = region_y + max_height
sorted_cols = sorted(column_top.keys())
for i, (xs, xe) in enumerate(sorted_cols):
    top_y = column_top[(xs, xe)]
    if region_top - top_y > self.kerf:
        left  = sorted_cols[i-1][1] if i > 0                  else region['x']
        right = sorted_cols[i+1][0] if i < len(sorted_cols)-1 else region['x'] + region['width']
        cuts.append({
            'direction': 'H',
            'position': top_y,
            'start': left,
            'end': right,
            'priority': region_priority_base + 15,
            'type': 'column_top_trim',
            'sub_priority': 0,
        })
```

### 왜 서브영역 경계(left/right)를 쓰는가

Guillotine 컷은 "현재 서브영역 전체 관통"이어야 함. 짧은 컬럼의 top trim이 그룹 자체 x 범위(x_start~x_end)만 관통하면 **또 다른 부분 컷 위반**이 됨(009에서 잘못 생각한 부분). 인접 컬럼이 이미 V 컷으로 분할되어 있으므로, 이 H 컷은 **앞뒤 V 컷 사이의 서브영역** 전체를 관통해야 함.

### priority

`piece_separation`·`right_trim`(priority = region_base+20+group_idx*10 ≥ 20)보다 먼저 실행되어야 하므로 `region_base+15`.

### dedup과의 관계

[_build_plate_from_regions 내 dedup](../src/woodcut/strategies/region_based.py) 이 `(direction, position, start, end)` 같은 컷을 제거. 첫째 행 stacked 컬럼의 `column_top_trim`은 `stacked_separation`과 동일 좌표가 될 수 있으나 dedup이 처리. 새 로직이 짧은 컬럼에 대해 **새로운** H 컷(stacked가 없는 x 범위)을 추가하는 것이 순 효과.

## 3. 변경 대상

| 파일 | 변경 |
|---|---|
| `src/woodcut/strategies/region_based.py` | `_pack_multi_group_region` secondary_row_trim 블록 뒤에 `column_top_trim` 로직 추가 |

(web_app/static/region_based.py는 symlink이므로 자동 동기화.)

## 4. 재사용

- 그룹 리스트, `max_height_in_region`, `region_y`는 이미 계산되어 있음.
- `self.kerf`, `region['x']`, `region['width']` 기존 인프라.
- dedup 로직(009)이 중복 제거.

## 5. 검증 계획

### 수치 검증
- 재현 케이스: Sheet 1 cut list에 `column_top_trim pos=764, start=2000, end=2440` 존재.
- V#6·#7의 end=764는 유지 (오른쪽-아래 서브영역 전체 관통이 됨).

### 시각적 검증
- Sheet 1 PNG: 100×764 위쪽 y=764에 빨간 H 선이 x=2000~2440 구간에 그려짐.
- 기존 컷은 그대로, Guillotine 계층 구조 명확.

### 회귀 테스트
- baseline 11조각 (회전 허용/불허).
- 협탁 preset.
- 004/005 시나리오.

### 제약 조건
- 모든 H 컷이 자신의 서브영역 전체 관통.
- kerf 5mm 존중.
- ±1mm 정확성.

### 엣지 케이스
- 모든 컬럼이 동일 top → trim 컷 발동 안 함.
- 단일 컬럼 region → sorted_cols 길이 1, left=region_x, right=region_x_end.
- stacked 없이 가로 그룹만 있는 region → 기존 경로와 동일 결과.

## 6. 알려진 한계

- 짧은 컬럼이 **region 중앙**에 있고 좌우 모두 stacked로 둘러싸이면 start/end 모두 인접 컬럼 경계 — OK.
- 스킵 조건이 `region_top - top_y > kerf` 단순 비교 — region_trim과 일관.

## 7. 구현 순서

- [ ] 10-1. `_pack_multi_group_region` column_top 로직 추가.
- [ ] 10-2. 재현 케이스 cut list 검증.
- [ ] 10-3. 시각화 PNG 확인.
- [ ] 10-4. 회귀 (baseline 11 / hyuptag).
- [ ] 10-5. 커밋.
