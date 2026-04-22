# Woodcut - 목재 재단 최적화

## 프로젝트 개요

Guillotine Cut 제약 하에서 목재/MDF 원판에 조각들을 효율적으로 배치하고 절단 순서를 생성하는 최적화 도구

- **목표**: 최소 판 수로 모든 조각 배치, 실제 작업 가능한 절단 순서 생성
- **제약**: Guillotine Cut (영역 전체 관통 직선 절단), 톱날 두께 5mm, 회전 선택 가능
- **입출력**: 조각 목록 입력 → 배치도 + 절단 순서 + PNG 시각화

---

## 현재 구현

### RegionBasedPacker (유일한 전략)

**핵심 개념:**
- **다중 그룹 영역 배치**: 한 영역에 여러 그룹 배치
- **정확한 그룹화**: 정확히 같은 크기끼리 그룹화 후 회전 옵션 생성
- **백트래킹 최적화**: 모든 그룹을 배치할 수 있는 최적 영역 조합 탐색
- **통합 절단**: 영역 분할 자체가 Guillotine 컷 — `GNode` 트리 한 장으로 표현 (`.solution/011`).

**참조**: 상세 알고리즘은 [ALGORITHM.md](ALGORITHM.md) 참조

---

## Guillotine Tree (`.solution/011`)

길로틴 절단 순서는 **영역 분할 트리 자체**가 보장한다. priority 숫자 조정 없음.

**노드 (`GNode`)**:
- 각 internal 노드는 자기 직사각형을 관통하는 컷 1개를 나타냄 (방향 H/V + 위치).
- first/second 자식은 컷을 기준으로 정확히 양분된 서브직사각형 (kerf 포함).
- leaf는 piece 또는 scrap.

**빌드 & emit**:
- plate 루트에서 region 경계를 H 컷 연쇄로 skeleton 구축.
- 각 region 안에서 재귀 guillotine partitioning — `_build_region_subtree`가 placed 좌표만 보고 V/H 후보를 찾아 분해.
- 전위 순회(parent → first → second)로 cut 리스트 emit. order = 순회 순서, start/end = 노드 직사각형에서 자동 유도.

**불변식**: `validate_guillotine(plate_root)` 가 매 `_build_plate_from_regions` 끝에서 디버그 assertion으로 확인.

**결과**: start/end 불일치·순서 역전·중복 dedup 모두 자료구조가 애초에 허용하지 않음.

---

## 테스트 결과

### 테스트 케이스 (11개 조각)
- 800×310 (2개), 644×310 (3개), 371×270 (4개), 369×640 (2개)

### 회전 허용
- **원판**: 1장
- **배치율**: 11/11 (100%)
- **사용률**: 66.1%
- **절단**: 17회 (길로틴 순서 준수)

### 회전 불허
- **원판**: 1장 (.solution/008 k-격자 variants로 2→1장 개선)
- **배치율**: 11/11 (100%)
- **사용률**: 66.1%
- **절단**: 19회

---

## 사용 방법

### CLI 실행
```bash
# 기본 실행
uv run woodcut

# 빌드 후 실행
uv build
woodcut
```

### 입력
대화형으로 입력: 원판 너비/높이(mm), kerf(mm), 회전 허용(y/n)

### 출력
- 콘솔: 배치 요약, 절단 순서, 검증 결과
- PNG: `output/cutting_plan_region_based_<timestamp>.png`

---

## 프로젝트 구조

```
woodcut/
├── src/woodcut/
│   ├── cli.py              # CLI 진입점
│   ├── interactive.py      # 대화형 모드
│   ├── visualizer.py       # 시각화
│   └── strategies/
│       └── region_based.py # RegionBasedPacker
├── ALGORITHM.md            # 알고리즘 상세
├── AGENTS.md               # AI 개발 가이드
└── PLAN.md                 # 이 문서
```

---

## 주요 버전 히스토리

### v1.0.0 - RegionBasedPacker (2025-12-27)
- 다중 그룹 영역 배치 구현
- 다중 판 지원
- 전략 1~5 삭제, RegionBasedPacker만 유지

### v2.0.0 - 길로틴 절단 통합 (2025-12-31)
- 배치와 절단 통합 (FSM 제거)
- 우선순위 시스템으로 길로틴 원칙 준수
- 절단선 11개 → 15개 (완전 분리 + 자투리 trim)

### v3.0.0 - Two-Tier Priority (2026-01-04)
- 전역/지역 우선순위 분리
- 영역 경계 우선 실행으로 길로틴 위반 해결

---

## 향후 개선 (단기)

- [ ] 다단 배치 지원 - 옵션 기반, 보수적 (상세: [.solution/002](.solution/002-20260104-multi-tier-placement.md))
- [ ] CSV/JSON 입력 지원
- [ ] 웹 UI 개선

---

## 멀티 사이즈 원판 지원 (2026-04-18)

서로 다른 규격 원판을 각기 정해진 수량만큼 보유한 상태에서 Best-Fit Lookahead + 판 수 최소화 편향으로 재단 계획 생성.

- **입력**: `stocks=[(width, height, count), ...]`
- **선택 규칙**: 매 iteration 마다 각 남은 stock 종류를 1장 시뮬레이션 후 `(pieces_placed, utilization)` 사전식 비교로 최적 stock 선택
- **편향**: utilization만으로는 작은 원판 여러 장에 빽빽이 채우는 결과를 선호하게 됨. `pieces_placed` 우선은 "한 장에 많이 들어가면 그 한 장을 쓴다"는 실무 직관을 보존
- **Stock 고갈·초과 조각**: 남은 조각이 모든 stock에 배치되지 못하면 즉시 종료 (무한루프 방지)

---

## Occupancy 기반 겹침 방지 (2026-04-19)

Stacked 그룹 위로 덮어쓰는 P0 겹침 버그 수정.

- **신규**: `src/woodcut/strategies/rect.py` — `Rect` + `intersects/contains/split_guillotine`
- **신규**: `_init_region_occupancy(regions)` — region에 `occupied: list[Rect]`/`free_rects: list[Rect]` 필드 채움. **stacked 그룹은 count개의 Rect로 따로 기록**이 핵심(Phase A 직후 실행).
- **수정**: `_optimize_trim_placement` — stacked anchor 그룹의 column 위에 trim 공간이 있다고 가정하지 않음(건너뜀). trim_rows 추가 전 `occupied`와 교차 여부 방어 assert.
- **스키마**: `trim_rows[*]`에 선택 필드 `x_offset`(기본 0). cut 생성 로직도 한 줄 반영(line 706).
- **회귀 방지**: `tests/test_overlap_detection.py` — 조각 쌍 bounding box 교차 여부를 직접 검사하는 헬퍼 + P0/협탁/기본 회전 3 케이스.

후속: 완전 occupancy 기반 백트래킹·stacked column 최상단 위 trim 허용은 범위 밖.

---

## 원판 재고 부족 시 명시 리포트 (2026-04-18)

`RegionBasedPacker.pack()`는 이제 `(plates, unplaced)` 튜플을 반환한다.

- **반환 형태**: `pack()` → `tuple[list[dict], list[dict]]`
  - `plates`: 기존과 동일한 배치 결과
  - `unplaced`: 재고 부족·크기 초과로 배치되지 못한 조각 dict 리스트
- **CLI**: 미배치 조각이 있으면 크기별 집계와 함께 `⚠️  원판 재고 부족` 경고 출력
- **Web API**: `CuttingResponse.unplaced_pieces`에 리스트 포함, `success = len(unplaced) == 0`
- **Web UI**: 결과 화면 상단에 미배치 조각 경고 배너 렌더링

사용자가 재고가 부족한 사실을 모르고 재단에 착수하는 위험을 방지.

---

## 부분 count stacking (.solution/008, 2026-04-22)

Phase A anchor backtracking이 `count` 통째로만 variant를 만들던 제약을 풀어 큰 그룹을 여러 plate/region으로 분할 배치.

- **`_flatten_group_options`**: `{min(count, k_max), count//2, count//4, …, 1}` 격자로 k-variant 생성. `k_max`는 plate width/height 대비 물리 상한.
- **`_allocate_anchor_backtrack`**: `used_groups: set` → `remaining_counts: dict[original_size, int]`로 교체. 같은 원본을 여러 region에서 재소비 가능 (단 같은 region 내 중복은 금지).
- **`_build_region_with_anchor`**: `already_used: set` → `remaining_counts: dict`, 반환 `used_sizes: set` → `consumed: dict`.
- **결과**: 760×260 ×14 같은 "plate 한 장 통째론 안 들어감" 그룹이 Phase A 탈락하지 않고 부분 배치됨. 재현 케이스(2000×280 ×4 + 760×260 ×14 + 100×764 ×2)에서 회전 허용 시 Sheet 1 6→14개, 미배치 2→1개. baseline 11조각(회전 불허)은 2→1 plate로 개선.

---

## 솔루션 문서

프로젝트의 주요 개선 작업들은 `.solution/` 디렉터리에 별도 문서화:

- [001: Guillotine 절단 통합](.solution/001-20251231-guillotine-cutting-integration.md) - 배치와 절단 통합, Two-Tier Priority 시스템
- [002: 다단 배치](.solution/002-20260104-multi-tier-placement.md) - 남은 공간 활용 (계획 단계)
- [004: 멀티 사이즈 원판](.solution/004-20260418-multi-size-stocks-plan.md) - Best-Fit Lookahead + 사전식 편향
- [005: 원판 재고 부족 리포트](.solution/005-20260418-stock-shortage-reporting.md) - `pack()` 반환 튜플화 + CLI/API/UI 경고
- [006: Occupancy 기반 겹침 방지](.solution/006-20260419-occupancy-hierarchical-backtracking.md) - `Rect` + `occupied` 필드, stacked trim 겹침 P0 수정
- [008: 부분 count stacking](.solution/008-20260421-partial-count-stacking.md) - k 격자 variant + remaining_counts 추적
- [011: Guillotine tree 통합](.solution/011-20260421-guillotine-tree-refactor.md) - 영역/컷 일원화, dict cut emit 삭제

---

## 기술 스택

- **Python 3.10+** (match-case, 타입 힌트, walrus 연산자)
- **matplotlib** (시각화)
- **uv** (패키지 관리)
