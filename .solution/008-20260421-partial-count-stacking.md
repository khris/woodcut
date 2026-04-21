# 부분 count stacking으로 그룹 분할 허용 — 디자인 + 구현 플랜

- **작성일**: 2026-04-21
- **작성자**: Hong Segi + Claude
- **상태**: 승인됨
- **관련 스펙**: [006-occupancy-hierarchical-backtracking](006-20260419-occupancy-hierarchical-backtracking.md), [007-fallback-trim-accuracy](007-20260421-fallback-trim-accuracy.md) (선행)

## 1. 배경과 목표

### 재현 케이스 (007과 동일 입력)

- Stock: 2440×1220 ×2, 회전 허용
- Pieces: 2000×280 ×4, 760×260 ×14, 100×764 ×2

### 증상

Sheet 1에서 760×260 조각이 **전혀 배치되지 않음**. 오른쪽 (x≈2215~2440) 영역이 비어 있는데도 활용 실패.

실제로는 Sheet 1에 760×260 회전본(260×760) 몇 개를 꽂을 수 있는 공간이 존재하지만 anchor backtracking이 `count=14`를 **통째로** 하나의 variant로만 취급해 넣지 못함.

### 원인

[region_based.py:328-389](../src/woodcut/strategies/region_based.py:328) `_flatten_group_options`:

```python
# 가로 배치: count 전체가 한 줄
total_width_h = (w + self.kerf) * count   # 14*(760+5) = 10710

# 세로 배치: count 전체가 한 컬럼 (total_width_h > plate_width 일 때만)
total_height_v = (h + self.kerf) * count  # 14*(260+5) = 3710  ← plate_height(1220) 초과
```

즉 count=14 그룹은 "14×가로" 아니면 "14×세로" 둘 다 불가능하여 **variant가 하나도 없이** Phase A에서 탈락. 그룹을 `k < count`개로 쪼개는 옵션이 설계 자체에 없음.

### 목표

1. Phase A anchor backtracking이 **큰 그룹을 자동으로 부분 배치**할 수 있게 variant 확장.
2. 재현 케이스에서 Sheet 1에 760×260 일부(가능한 만큼)가 들어가 활용률 개선, Sheet 2 나머지 처리.
3. 기존 "작업 편의성(같은 크기 그룹화)" 철학 유지 — 무작위 파편화가 아니라 **의미 있는 단위(column/row 단위)로만 분할**.

## 2. 설계 결정

### 핵심: stacked variant에 `k` 파라미터 도입

기존 variant가 `count` 고정이었다면, 이제 **같은 원본 크기에 대해 여러 count 옵션** 생성:

```python
# k = count, count-1, count-2, ... 까지 (또는 감소폭 커지는 전략)
for k in range(count, 0, -1):
    # stacked_h (column)
    total_h_v = (h + kerf) * k
    if total_h_v <= plate_height:
        variants.append({
            'original_size': (w, h),
            'count': k,           # 이 variant가 차지하는 조각 수
            'rotated': rotated,
            'stacked': True,
            'height': total_h_v,
            'width': w,
            'total_width': w + kerf,
        })
    # 가로 k-chunk
    total_w_h = (w + kerf) * k
    if total_w_h <= plate_width:
        variants.append({
            'original_size': (w, h),
            'count': k,
            'rotated': rotated,
            'stacked': False,
            'height': h,
            'width': w,
            'total_width': total_w_h,
        })
```

그리고 anchor backtracking이 **같은 `original_size`의 남은 count를 다음 plate나 다음 region으로 이월**할 수 있게 사용량을 추적:

- `used_groups: set[original_size]` → **`remaining_counts: dict[original_size, int]`** 로 교체
- 한 plate 안에서 같은 원본의 variant를 여러 번 소비 가능 (단, 같은 region 안 중복은 기존처럼 금지)
- plate 경계를 넘어 다음 plate로 남은 count 이월

### 탐색 폭발 제어

`k = 1..count` 전부 variant로 만들면 백트래킹 가지가 폭발. 다음 휴리스틱으로 제한:

1. **k는 격자(stride)로만 생성**: 예 `k ∈ {count, count//2, count//4, ..., 1}` (≤ log₂ count 개).
2. **stacked는 `plate_height`에 맞는 최대 k 우선** — `k_max = (plate_height - kerf) // (h + kerf)`로 상한 설정.
3. **가로는 `plate_width`에 맞는 최대 k 우선** — `k_max = plate_width // (w + kerf)`로 상한.
4. anchor backtracking은 상한 variant를 먼저 시도하고 실패 시 하향.

### region 내 remaining_counts 추적

- `_build_region_with_anchor`: 앵커 k만큼 소비, compatible 그룹도 k_compat 만큼 소비.
- 반환값 `used_original_sizes` → **`consumed: dict[original_size, int]`**로 변경.
- top-level `backtrack(remaining_counts, y_offset)`가 remaining_counts를 업데이트하며 재귀.

### plate 간 이월

`_pack_single_plate`는 기존처럼 1 plate 결과만 반환하되 `remaining_pieces`에서 실제 배치된 조각만 차감 — 멀티 plate 루프([region_based.py:71-134](../src/woodcut/strategies/region_based.py:71))가 자동으로 남은 조각을 다음 iteration에 전달하므로 변경 불필요.

### 대안 검토

- **가로 chunk 없이 stacked만 k 도입**: 그룹이 세로가 안 맞고 가로도 너무 넓을 때는 해결 불가. 가로 k도 필요.
- **동적 k 선택 (greedy, 휴리스틱 O(1))**: 단순하지만 backtracking의 최적성을 잃음. 기존 backtracking과 일관된 방식으로 k를 탐색 축에 편입.

## 3. 변경 대상

| 파일 | 변경 |
|---|---|
| `src/woodcut/strategies/region_based.py` | `_flatten_group_options`: k 격자 variant 생성 (가로/세로 양쪽) |
| 동 | `_build_region_with_anchor`: `consumed` dict 반환, `already_used` → `remaining_counts` 파라미터 |
| 동 | `_allocate_anchor_backtrack`: `used_groups` set → `remaining_counts` dict. 종료 조건 `all(c == 0)` |
| 동 | occupancy 초기화(`_init_region_occupancy`): stacked k에 맞는 Rect k개 기록 (기존 로직 연장) |
| 동 | `_pack_multi_group_region`: 그룹 count가 variant의 k (< 원본 count)일 때도 동작 검증 |
| `.solution/006-...md` | "부분 count stacking 이후" 후속 참조 추가 (한 줄) |
| `tests/` 또는 CLI 스모크 | 재현 케이스 회귀 + 기존 회귀 보강 |

## 4. 재사용

- 기존 `Rect`/occupancy 모델(006)을 그대로 사용 — k개의 Rect를 stacked column에 순차 기록.
- Phase B trim 최적화는 occupancy를 이미 존중하므로 변경 없음.
- `expand_pieces`와 remaining 차감 로직(top-level)은 변경 없음.

## 5. 검증 계획

### 수치 검증
- 재현 케이스: Sheet 1에 2000×280 ×4 + 100×764 ×2 외에 **760×260 일부** 추가 배치 (예상 4개 이상), Sheet 2에 나머지 배치.
- 총합 20개 ≥ 기존 결과(실질 6+12=18, 2개 미배치)보다 개선.
- 모든 배치 조각의 `placed_w/h`가 원본(회전 고려) ±1mm.

### 시각적 검증
- Sheet 1 PNG: 오른쪽 여백에 260×760 세로 조각 column 최소 1개 존재.
- 오버랩 없음, 절단선이 Guillotine 제약 준수.

### 회귀 테스트
- 회전 허용/불허 기본 케이스 (11/11).
- 협탁 preset.
- 004 멀티 stock, 005 stock-shortage.
- **007 fallback 케이스 유지** — Phase A 개선 후에도 일부 입력은 fallback 진입할 수 있으므로 fallback 무결성 계속 보장.

### 제약 조건
- Guillotine 관통 절단.
- kerf 5mm.
- ±1mm.

### 엣지 케이스
- 매우 큰 count (e.g. 50개) — k 격자 덕에 백트래킹 시간 폭발 없음 (O(log count) variants).
- count=1 그룹 — 기존 동작과 동일.
- 정확히 plate에 맞는 count — 풀 stacked variant 선택.

### 성능
- k 격자로 variant 수 상한 ≈ 그룹당 log₂ count 정도 → backtracking 탐색 공간 로그 스케일 증가. AGENTS.md "조각 ~50개 수 초" 범위 유지 확인.

## 6. 알려진 한계

- k 격자는 완전 탐색이 아님 — 이론상 놓치는 최적 배치 존재 가능 (예: k=7이 최적이지만 격자가 {14,7,3,1}이면 걸림). 이 경우 k_max 상한과 격자 밀도를 조정.
- 같은 `original_size`를 한 region 안에 **두 variant로 동시 배치**(e.g. stacked 4개 + 가로 3개)까지는 다루지 않음 — 이후 개선 후보.
- Phase A가 빈 regions를 반환하는 경우는 여전히 fallback(007)로 귀결.

## 7. 구현 순서

- [ ] 8-1. 007 선행 완료 확인 (fallback 무결성이 있어야 Phase A 실험 시 안전망 유지).
- [ ] 8-2. `_flatten_group_options`에 k 격자 variant 생성 로직 추가 + 단위 수준 smoke.
- [ ] 8-3. anchor backtracking을 `remaining_counts` 기반으로 수정 (재귀 시그니처 변경).
- [ ] 8-4. `_build_region_with_anchor` 반환/소비 로직 업데이트.
- [ ] 8-5. occupancy 초기화에서 stacked k개 Rect 기록 확인.
- [ ] 8-6. 재현 케이스 실행 → Sheet 1에 760×260 추가 배치 확인.
- [ ] 8-7. 기본 회전 허용/불허 회귀.
- [ ] 8-8. 협탁 preset + 004/005 회귀.
- [ ] 8-9. 시각화 PNG 육안 확인.
- [ ] 8-10. AGENTS.md "자주 하는 실수" 항목에 "그룹 전체 count 고정 가정" 경고 한 줄 + PLAN.md 업데이트.
- [ ] 8-11. 커밋: `feat(packer): allow partial-count stacking in anchor backtracking`
