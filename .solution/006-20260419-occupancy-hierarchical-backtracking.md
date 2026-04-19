# Phase B 재작성: occupancy 기반 계층형 백트래킹 — 디자인 + 구현 플랜

- **작성일**: 2026-04-19
- **작성자**: Hong Segi (khris@khrislog.net) + Claude
- **상태**: 진행 중 (사용자 승인 2026-04-19)
- **관련 스펙**: `.solution/002-20260104-multi-tier-placement.md`, `.solution/003-20260110-verification-checklist.md`

## 1. 배경과 문제

회전 불허로 `2000×280 × 2` + `760×260 × 7` + `764×100 × 1`을 원판 `2440×1220` 한 장에 돌리면 배치된 조각 중 두 개가 **정확히 같은 좌표 (0, 285)** 에 놓여 물리적으로 겹친다. 기존 "조각 크기 검증"은 개별 조각의 W/H만 보므로 "✅ 모든 조각이 정확한 크기"를 조용히 통과시킨다.

```
조각 크기 검증 (상세):
  [2] ✓ 위치: (0,285), 필요: 2000×280
  [3] ✓ 위치: (0,285), 필요: 764×100   ← 겹침!
```

### 근본 원인

[`_optimize_trim_placement` (region_based.py:969-1095)](../src/woodcut/strategies/region_based.py)는 region을 "row 하나 + `max_height`"라는 추상으로만 본다. 같은 row 안에 `stacked=True` 그룹 (예: 2000×280을 세로로 쌓은 한 컬럼) 이 들어 있으면 그 컬럼은 실제로 **두 개의 rect**를 점유하는데, trim 최적화는 이 내부 구조를 모르고 `y_offset = piece_h + kerf` 한 줄만 계산해 두 번째로 쌓인 조각 위에 다른 그룹을 덮어씌운다.

- 공간 모델이 없다 → trim 최적화·scrap 재활용·multi-tier 각 패스가 좌표를 독립적으로 재계산
- stacked·앵커 같은 개념은 "row 하나" 가정을 구제하려는 특수 케이스였는데, 그 특수 케이스가 다른 패스와 결합할 때 충돌이 숨어든다.

## 2. 설계 결정

### 2.1 공간 모델 명시화 — `occupied` / `free_rects`

Region dict에 두 필드를 도입한다.

```python
region = {
    ..., 'rows': [...], 'trim_rows(dynamic)': ...,
    'occupied': list[Rect],    # 이미 배치된 조각 bounding box (region 좌표계)
    'free_rects': list[Rect],  # 남은 빈 공간 (guillotine-valid split)
}
```

**stacked 그룹은 count 개의 Rect로 따로 기록**한다 — 이것이 버그의 근본 수정 지점. 한 덩어리가 아닌 여러 Rect로 표현되므로 이후 어떤 패스도 그 사이에 다른 조각을 끼워넣을 수 없다.

### 2.2 Phase B를 백트래킹으로 재작성

- **Phase A** (`_allocate_anchor_backtrack`) — 유지. 앵커 기반 region 할당은 그대로.
- **Phase B** (`_optimize_trim_placement`) — occupancy 기반 백트래킹으로 교체.
- **Cut 생성** (`_pack_multi_group_region`, 380줄) — 유지. 기존 `trim_rows` 스키마를 소비하는 380줄 로직은 손대지 않는다.

### 2.3 계층형 유지 (통합형 X)

Phase A + B를 합친 통합 백트래킹은 탐색 공간이 폭발한다. 계층형은 각 트리가 작고, 기존 Phase A를 그대로 재사용 가능. "이번 작업은 겹침 버그 수정 + 기존 수준 밀도 유지"가 목표이므로 앵커 선택 재튜닝은 범위 밖.

### 2.4 탐색 순서: 한 줄 우선, 안 되면 여러 줄

사용자 결정. 백트래킹 분기 순서에서:
1. 기존 한 줄 `trim_rows` 엔트리에 가로로 이어붙이는 배치를 **먼저** 시도
2. 새 엔트리(다른 y)를 만드는 배치는 **그 다음** 시도

### 2.5 `trim_rows` 스키마 확장 — 선택적 `x_offset`

같은 trim strip 안에 y가 다른 배치 (2줄 이상) 를 표현하려면 각 엔트리의 x 시작점이 필요하다. 기존 엔트리는 `x_offset=0`으로 간주하므로 호환성 무손상.

```python
group['trim_rows'] = [
    {'y_offset': 0, 'groups': [...], 'height': 260, 'x_offset': 0},      # 기본
    {'y_offset': 265, 'groups': [...], 'height': 260, 'x_offset': 0},    # 2줄째
]
```

Cut 생성 로직([line ~706](../src/woodcut/strategies/region_based.py))의 `trim_x = group_start_x`를 `trim_x = group_start_x + row.get('x_offset', 0)`으로 수정 — 한 줄 변경.

### 2.6 타임아웃 없음

사용자 결정. 가지치기(면적 상한, 초기 greedy lower bound)만으로 방어한다. 50+ 조각 대형 케이스에서 실제 느려지면 그 때 후속 작업.

## 3. 변경 대상

| 상태 | 경로 | 변경 내용 |
|------|------|----------|
| 신규 | `src/woodcut/strategies/rect.py` | `Rect` 데이터클래스 + `intersects/contains/split_guillotine` |
| 수정 | `src/woodcut/strategies/region_based.py` | `_init_region_occupancy` 추가, `_optimize_trim_placement` 백트래킹 재작성, `trim_rows` `x_offset` 지원 |
| 신규 | `tests/test_overlap_detection.py` | 겹침 검증 헬퍼 + 3 회귀 케이스 |
| 수정 | `AGENTS.md` | "자주 하는 실수"에 stacked occupied 기록 규칙 추가 |
| 수정 | `PLAN.md` | Phase B 백트래킹 섹션 추가 |
| 무변경 | `src/woodcut/strategies/region_based_split.py` | `_try_pack_groups`가 부모 함수 호출만 하므로 자동 반영 |

## 4. 재사용

- `_allocate_anchor_backtrack`(line ~385) — Phase A로 재사용
- `_pack_multi_group_region`(line 578-957) — Cut 생성 그대로 사용, line ~706 한 줄만 수정
- `_build_plate_from_regions`(line 183) — regions→plate 변환 재사용
- 현 `_optimize_trim_placement`의 FFDH 유사 greedy 로직 — 초기 lower bound 용으로 함수 추출

## 5. 구현 순서

1. **회귀 방지선**: `tests/test_overlap_detection.py` 신규
   - 헬퍼 `assert_no_piece_overlap(plate)`
   - 케이스 1 (P0 버그), 케이스 2 (협탁), 케이스 3 (기본 회전)
   - 현재 코드에서 케이스 1은 **fail**, 2·3은 pass 해야 함
2. **인프라**: `Rect` 유틸 + `_init_region_occupancy` 추가
   - 기능 변화 없음, 기존 테스트 전부 유지 + 케이스 1은 여전히 fail
3. **Phase B 재작성**: `_optimize_trim_placement` 본체 교체 + `x_offset` 어댑터
   - 케이스 1 pass, 기존 테스트 회귀 없음
4. **정리**: `AGENTS.md`/`PLAN.md` 문서화, `.solution/006` 상태를 완료로 갱신

## 6. 검증 계획 (AGENTS.md 5단계 체크리스트 적용)

### 6.1 수치 검증 — pytest

```bash
uv run pytest                                           # 전체
uv run pytest tests/test_overlap_detection.py -v        # 신규
uv run pytest tests/test_multi_stock_integration.py -v  # 회귀
```

- 불변식: `placed + len(unplaced) == total`
- 추가 불변식: `assert_no_piece_overlap(plate)` 모든 plate

### 6.2 시각적 검증 — CLI 스모크

```bash
# P0 버그 케이스
printf "2440\n1220\n1\n\n5\nn\n2000\n280\n2\n760\n260\n7\n764\n100\n1\n\n" | uv run woodcut 2>&1 | tee /tmp/woodcut_p0.log
grep -q "겹침 없음" /tmp/woodcut_p0.log  # 또는 "모든 조각이 정확한 크기"만이라도 오류 없음

# 협탁 회귀
echo -e "2440\n1220\n10\n\n5\nn\n560\n350\n2\n446\n50\n2\n369\n50\n2\n550\n450\n1\n450\n100\n1\n450\n332\n2\n450\n278\n1\n\n" | uv run woodcut 2>&1 | tee /tmp/woodcut_hyuptag.log
! grep -q "원판 재고 부족" /tmp/woodcut_hyuptag.log
```

### 6.3 회귀 테스트

- 협탁, 기본 회전 — 기존과 동일 배치 유지
- 회전 허용/불허 양쪽
- `RegionBasedPackerWithSplit` 경로도 한 번 (split 오버라이드가 무변경임을 확인)

### 6.4 제약 조건

- Guillotine cut / kerf / ±1mm 치수 정확성 — 기존과 동일 (Cut 생성 로직 무변경)

### 6.5 엣지 케이스

- stacked 그룹이 없는 region (순수 수평 배치만) → `occupied`에 rect 1개씩, 기존 결과와 동일
- 모든 조각이 한 region에 들어가는 작은 케이스 → Phase B가 할 일 없이 no-op

## 7. 리스크 & 미결정

- **Cut 생성 어댑터 mismatch**: `x_offset` 확장으로 line 706 외에 영향이 있으면 (예: 2차 H컷 range 계산 line 778-810) 수정 범위가 살짝 늘 수 있음. 3단계 중 실측.
- **탐색 폭발 가능성**: 현재 테스트는 밀리초지만 50+ 조각 미검증. 가지치기 부족 시 후속 작업.
- **Phase A suboptimal**: 앵커 선택이 나쁜 경우 Phase B 만회에 한계. 이 작업의 범위 밖.

## 8. 알려진 한계

- Phase A는 여전히 row 기반 추상에서 출발하므로 "한 region에 여러 row" 같은 본격적인 2D 배치는 불가. 이건 Phase A 자체를 occupancy 기반으로 바꾸는 별도 큰 작업.
- stacked·앵커 개념은 내부적으로 남음 (Phase A 소속). Phase B는 그 위에서 정확히 동작.

## 9. 알고리즘 개념도

```
입력 pieces
  ↓ 그룹화 (exact size) → variants (horizontal / stacked)
  ↓ [Phase A] 앵커 백트래킹 영역 할당        ← 유지
  ↓ [Phase A+] _init_region_occupancy        ← 신규: occupied/free_rects 채우기
  ↓ [Phase B] occupancy 백트래킹 재배치       ← 재작성 (구 _optimize_trim_placement)
                └ 한 줄 우선 → 안 되면 여러 줄
                └ 가지치기: 면적 상한 + greedy lower bound
                └ 어댑터: 결과를 trim_rows(+x_offset) 스키마로 변환
  ↓ Cut 생성 (_pack_multi_group_region)       ← 유지 (line 706 한 줄만 수정)
  ↓ 시각화 + 검증 (겹침 검증 포함)
```
