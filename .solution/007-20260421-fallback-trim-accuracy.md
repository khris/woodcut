# Fallback 경로 정확성 복구 — 디자인 + 구현 플랜

- **작성일**: 2026-04-21
- **작성자**: Hong Segi + Claude
- **상태**: 승인됨
- **관련 스펙**: [006-occupancy-hierarchical-backtracking](006-20260419-occupancy-hierarchical-backtracking.md) (Phase B occupancy 모델)

## 1. 배경과 목표

### 재현 케이스

- Stock: 2440×1220 ×2, 회전 허용
- Pieces: 2000×280 ×4, 760×260 ×14, 100×764 ×2

### 증상

Sheet 2 배치 결과에서 조각이 **잘못된 크기**로 기록됨:

```
(265,0)  placed=260x495  orig=760x260 rot=True   ← 760→495 로 잘림
(530,0)  placed=260x230  orig=760x260 rot=True   ← 760→230 로 잘림
(1060,0) placed=260x495  orig=760x260 rot=True
(1325,0) placed=260x230  orig=760x260 rot=True
...
총 14개 중 12개만 (그중 6개는 잘못된 크기), 2개 미배치
```

### 원인

Sheet 2에서 `_allocate_anchor_backtrack()`가 14개 그룹을 anchor로 받아들이지 못해 `regions = []` 반환
→ [region_based.py:168-185](../src/woodcut/strategies/region_based.py:168) fallback 경로 진입
→ `_find_best_placement_simple` + `_apply_placement`로 배치 후 `self.generate_guillotine_cuts(plate)` 호출
→ [packing.py:485-517](../src/woodcut/packing.py:485) `_split_region`의 트리밍 로직이 조각을 "분할한 영역 크기"로 간주해 `placed_h/w`를 덮어씀 (실제 조각은 원본 크기인데 `placed_h`만 축소)

fallback은 **영역 모델 없이 FreeSpace 평면 배치**를 하므로, 후속 Guillotine 분할이 조각의 실제 크기 대신 영역 경계로 trim을 유도한다. Phase A/Phase B(occupancy)의 보호를 받지 못하는 경로.

### 목표

1. fallback 경로가 생성하는 조각이 **항상 원본 크기(회전 고려) 그대로** `placed_w/h`를 가져야 한다 (±1mm 오차 허용, AGENTS.md 제약).
2. 공간이 부족해 일부 조각이 배치 불가능하면 그대로 `unplaced`로 넘기고, 배치된 조각은 반드시 무결한 크기.
3. 회귀 없음: 기존 회전 허용/불허 테스트, 협탁 preset, solution 001–006 시나리오 통과.

## 2. 설계 결정

### 핵심: fallback을 "occupancy 기반 shelf packer"로 교체

기존 `_find_best_placement_simple` + `generate_guillotine_cuts` 조합을 버리고, **fallback 전용의 단순 shelf/skyline 배치**로 대체한다. Phase A가 이미 구현한 region/occupancy 어휘를 재사용해 trimming이 필요없는 배치를 보장한다.

**선택 근거**
- `_split_region`의 trim 로직은 **Phase A가 미리 정렬해 둔 조각**에 대해 설계되었기에 fallback 순수 배치 결과에 적용하면 조각 무결성을 해침.
- Phase A의 anchor 백트래킹이 실패하는 주된 이유는 "그룹을 쪼개지 못함"인데, 이는 별도 플랜([008](./008-20260421-partial-count-stacking.md))에서 해결.
- fallback은 "최악의 경우 깨지지 않는 안전망"이어야 하므로, 단순·정확성 우선.

### 새 fallback 알고리즘 (Bottom-Left Shelf)

1. 조각을 면적 내림차순으로 정렬 (회전 포함 `(w, h)` 변형 각각 고려)
2. shelf 위로 왼→오 채우기, shelf 높이 = 첫 조각의 height, kerf 포함
3. 현재 shelf에 못 들어가면 새 shelf 시작 (y += shelf_h + kerf)
4. plate 상단 초과 시 해당 조각 skip → 호출자에 미배치로 반환
5. 배치된 각 조각의 `placed_w = w`, `placed_h = h` (회전 고려한 실제 크기)로 **명시 설정**

절단선은 shelf 경계(H)와 조각 간 경계(V)로 단순 생성 — trimming cut 불필요(크기가 정확하므로).

### 대안 검토

- **기존 `_split_region` 유지 + trim 금지 플래그**: 분기 추가는 의미 의존성이 커져 취약. 탈락.
- **Phase A에서 그룹 분할 강화**(=008)만으로 해결**: 분할 후에도 잔여 조각이 anchor가 안 되는 경우가 있어 fallback 자체의 안정성이 필요. 여전히 007 필요.

## 3. 변경 대상

| 파일 | 변경 |
|---|---|
| `src/woodcut/strategies/region_based.py` | fallback 블록 (168–185) 교체: 새 `_pack_fallback_shelf(remaining_pieces) -> dict` 도입. `_find_best_placement_simple`·`_apply_placement`·`generate_guillotine_cuts` 호출 제거 |
| `src/woodcut/strategies/region_based.py` | `_pack_fallback_shelf` 내부에서 `placed_w/h` 명시 설정. 절단선은 shelf 경계 + 조각 경계로 구성 |
| `src/woodcut/packing.py` | (변경 없음 — `_split_region` 경로는 Phase A 결과에만 계속 사용) |
| `tests/` 또는 CLI 스모크 | 재현 케이스 (2440×1220×2, 본문 pieces) 회귀 테스트 추가 |

## 4. 재사용

- `Rect`, `intersects` (`strategies/rect.py`): occupancy 기록 및 겹침 방어.
- kerf 상수, `self.plate_width/height`: 기존 `PackingStrategy` 기반.
- 절단선 dict 스키마 (`direction`, `position`, `start`, `end`, `priority`, `order`): 기존 visualizer가 그대로 소비.

## 5. 검증 계획

### 수치 검증
- 재현 케이스 20개 조각 중 배치 가능한 모든 조각이 **원본 크기 그대로** `placed_w/h`를 갖는지 확인.
- 2 plate 총합이 원본 pieces 수량(20)과 일치 또는 미배치(`unplaced`)로 정확히 귀속.

### 시각적 검증
- 시각화 PNG 2장(Sheet 1, Sheet 2) 확인: 오버랩 없음, 크기 라벨 일치 (✓).
- Sheet 2에서 260×760 조각이 **9개 column으로 전체 높이 차지** + 위 3개 가로 배치 형태가 아닌, shelf 단위로 깔끔한 직사각형.

### 회귀 테스트
- 회전 허용/불허 기본 테스트: `(800,310,2)+(644,310,3)+(371,270,4)+(369,640,2)` → 11/11 배치.
- 협탁 preset (memory `project_test_case_hyuptag`) 회전 불허 케이스.
- 멀티 stock 시나리오 (004).

### 제약 조건
- Guillotine: 모든 cut이 영역 전체 관통 (shelf 경계는 plate 전체 가로 관통, V cut은 shelf 세로 관통).
- Kerf 5mm 일관 적용.
- ±1mm 이내 정확성.

### 엣지 케이스
- fallback만으로 모든 조각이 공간 초과 → `unplaced`로 전부 넘어감.
- 단일 조각이 plate 최대 크기.
- 회전 불허 시 세로 기다란 조각이 shelf 1개 높이를 모두 차지.

## 6. 알려진 한계

- Shelf 배치는 bin-packing 최적이 아님 — 활용률은 Phase A(anchor backtrack)보다 낮을 수 있다. 이건 fallback의 목적(**정확성 안전망**)과 합치.
- Sheet 1처럼 Phase A가 성공한 경우는 이 코드 경로를 타지 않음 → 별도로 008에서 활용률 개선.

## 7. 구현 순서

- [ ] 7-1. 현재 fallback 코드 경로를 재현 케이스로 격리 실행하여 **회귀 스냅샷** 기록 (잘못된 `placed_h/w` 값 포함).
- [ ] 7-2. `_pack_fallback_shelf(remaining_pieces)` 구현 (shelf 배치, placed_w/h 명시 설정, cuts 생성).
- [ ] 7-3. `_pack_single_plate` fallback 블록 교체, 기존 호출 3개 제거.
- [ ] 7-4. 재현 케이스 수동 실행 → Sheet 2의 placed_h/w 무결성 확인.
- [ ] 7-5. 기본 회전 허용/불허 회귀 테스트 실행.
- [ ] 7-6. 협탁 preset 회귀 실행.
- [ ] 7-7. 시각화 PNG 육안 확인 (오버랩·크기 라벨).
- [ ] 7-8. AGENTS.md `.solution/` 참조 및 PLAN.md 필요 시 짧은 한 줄 추가.
- [ ] 7-9. 커밋: `fix(packer): replace fallback path with shelf packer to preserve piece size`
