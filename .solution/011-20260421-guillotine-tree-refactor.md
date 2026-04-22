# Guillotine Tree로 영역·컷 일원화 리팩토링 — 설계

- **작성일**: 2026-04-21
- **작성자**: Hong Segi + Claude
- **상태**: 구현 완료 (2026-04-22)
- **관련 스펙**: [006-occupancy-hierarchical-backtracking](006-20260419-occupancy-hierarchical-backtracking.md), [009-secondary-row-trim-bounds](009-20260421-secondary-row-trim-bounds.md), [010-column-top-guillotine-trim](010-20260421-column-top-guillotine-trim.md)

## 1. 배경과 문제의식

### 현재 구조 (실측)

[region_based.py](../src/woodcut/strategies/region_based.py) 2571 라인 단일 파일, `_pack_multi_group_region`만 417 라인([728-1144](../src/woodcut/strategies/region_based.py:728)).

cut을 emit하는 지점이 **25곳**(`grep "'type':"`). 구분:

| Phase | 함수 | 라인 | cut type |
|---|---|---|---|
| plate 경계 | `_build_plate_from_regions` | [758](../src/woodcut/strategies/region_based.py:758), [771](../src/woodcut/strategies/region_based.py:771) | scrap_boundary, region_boundary |
| 영역 내부 | `_pack_multi_group_region` | [787](../src/woodcut/strategies/region_based.py:787), [924](../src/woodcut/strategies/region_based.py:924), [954](../src/woodcut/strategies/region_based.py:954), [988](../src/woodcut/strategies/region_based.py:988), [1027](../src/woodcut/strategies/region_based.py:1027), [1042](../src/woodcut/strategies/region_based.py:1042), [1069](../src/woodcut/strategies/region_based.py:1069), [1094](../src/woodcut/strategies/region_based.py:1094), [1117](../src/woodcut/strategies/region_based.py:1117), [1130](../src/woodcut/strategies/region_based.py:1130) | tier_boundary, region_trim, secondary_row_trim, column_top_trim, right_trim, stacked_separation, piece_separation, group_boundary, group_trim |
| fallback | `_emit_fallback_cuts` | [364](../src/woodcut/strategies/region_based.py:364), [381](../src/woodcut/strategies/region_based.py:381) | shelf_boundary, shelf_column |
| (사용되지 않는 코드로 추정) | `_allocate_recursive_2d` 등 | [1707](../src/woodcut/strategies/region_based.py:1707)~[2221](../src/woodcut/strategies/region_based.py:2221) | 중복 type들 |

### 문제

1. **영역 분할 ↔ cut이 분리된 이중 구조**
   - `_allocate_anchor_backtrack`이 영역을 `regions[]` 리스트로 먼저 다 만들고,
   - `_pack_multi_group_region`이 사후에 10+ 분기로 cut을 emit.
   - 같은 경계선이 (a) 영역 경계(regions[i].y + height) (b) 컷(`region_boundary`, `tier_boundary`)로 **두 번 표현**.

2. **Guillotine 순서를 priority로 인위 조정**
   - `priority = region_priority_base + {10,15,20,23,25,...}` 같은 숫자 배틀이 cut별로 흩어져 있고, 그마저도 유효 서브영역 경계 관계를 반영하지 못해 [010](010-20260421-column-top-guillotine-trim.md)에서 `column_top_trim`이 V=2000(부모 컷)보다 먼저 정렬되는 역전 발생.
   - 정렬 후 `_build_plate_from_regions` 에서 dedup으로 덮고 있음 — 근본 아닌 임시방편.

3. **범위(start/end) 계산이 type별로 제각각**
   - `region['x'] + region['width']`([922](../src/woodcut/strategies/region_based.py:922), [1093](../src/woodcut/strategies/region_based.py:1093), [982](../src/woodcut/strategies/region_based.py:982), [1051](../src/woodcut/strategies/region_based.py:1051)), 그룹 x_end([951-952](../src/woodcut/strategies/region_based.py:951)), col_x_end([988](../src/woodcut/strategies/region_based.py:988)) 등 "이 컷이 속한 서브영역" 이란 관점이 코드 어디에도 명시 안 됨.
   - 009/010이 반복해서 "start/end를 어디로" 고친 건 본질이 관리 안 되는 증거.

4. **"서브영역" 1급 개념이 코드에 없음**
   - plate → region → row → group 계층은 있는데, V 컷으로 좌우 나눴을 때의 서브직사각형은 데이터로 존재 X.
   - 그래서 "오른쪽 서브영역 안에서만 관통하는 H" 같은 제약을 코드가 **표현하지 못함**.

### 목표

- **영역 분할이 곧 컷** 이라는 1:1 관계를 자료구조로 강제.
- cut의 start/end/priority/order가 **트리 구조에서 자동 유도**. 수동 지정 금지.
- Guillotine 제약이 **자료구조 불변식**으로 보장 (틀린 트리는 애초에 만들 수 없게).

## 2. 설계: Guillotine Tree

### 2.1 노드 정의

```python
@dataclass
class GNode:
    # 이 노드가 대표하는 직사각형 (plate 좌표)
    x: int; y: int; w: int; h: int

    # internal 노드: 분할 컷
    cut_dir: Literal['H', 'V'] | None = None  # None이면 leaf
    cut_pos: int | None = None                  # plate 좌표(절대)
    first: 'GNode | None' = None                # 분할 앞쪽 (H면 아래, V면 왼쪽)
    second: 'GNode | None' = None               # 분할 뒤쪽

    # leaf: 조각 혹은 스크랩
    piece: dict | None = None                   # placed piece dict
    kind: Literal['piece', 'scrap', 'kerf'] | None = None
```

**불변식**
- leaf 또는 (cut_dir, cut_pos, first, second) 모두 있음 — 둘 중 하나.
- V 컷: `first.x=x, first.w=cut_pos-x`, `second.x=cut_pos+kerf, second.w=x+w-(cut_pos+kerf)`.
- H 컷: 동일 논리 y/h.
- first/second 둘 다 `x, y, w, h`가 부모 내부에 속함.

이 불변식이 지켜지면 각 컷은 **자기 노드의 직사각형 전체를 관통** → Guillotine이 공리적으로 참.

### 2.2 Cut emit

트리 전위 순회(parent → first → second)로 cut 리스트 생성:

```python
def emit_cuts(node, kerf, out):
    if node.cut_dir is None:
        return
    out.append({
        'direction': node.cut_dir,
        'position': node.cut_pos,
        'start': node.x if node.cut_dir == 'H' else node.y,
        'end':   node.x + node.w if node.cut_dir == 'H' else node.y + node.h,
        'order': len(out) + 1,
        'region_x': node.x, 'region_y': node.y,
        'region_w': node.w, 'region_h': node.h,
    })
    emit_cuts(node.first, kerf, out)
    emit_cuts(node.second, kerf, out)
```

- start/end는 **노드의 x·w (또는 y·h)** 로 자동. type별 분기 불필요.
- order는 전위 순회 = Guillotine 실행 순서. priority 개념 삭제.
- dedup 불필요 (동일 컷이 중복 생길 수 없음 — 각 internal 노드가 컷 하나).

### 2.3 트리 빌드

1. **plate 루트** `GNode(0, 0, plate_w, plate_h)`.
2. 조각 그룹과 남은 영역을 입력으로 받아 **재귀적으로 split 선택**:
   - 현재 리프의 빈 직사각형에 들어갈 수 있는 그룹 중 하나를 선택.
   - 그룹의 bounding box를 떼어낼 수 있는 **컷 방향·위치** 결정 (예: 스크랩을 위로 떼려면 H, 왼쪽을 떼려면 V).
   - split 실행 → first/second 자식 생성 → 각 자식에 재귀.
3. 조각을 포함하는 가장 작은 리프에 `piece` 할당.
4. 더 이상 배치할 게 없으면 스크랩 리프로 종료.

### 2.4 기존 알고리즘과의 대응

| 기존 개념 | tree 표현 |
|---|---|
| region = horizontal row | 루트의 H 컷으로 분할된 자식 노드 |
| row 내 그룹들 | 그 자식 노드의 V 컷 연쇄 |
| stacked column | 더 깊은 H 컷 연쇄 |
| secondary row trim | 그룹 자식 내부의 H 컷 (자식 경계 내부 자동 관통) |
| column top trim | 오른쪽 서브트리 안의 H 컷 |
| region scrap | 플레이트 분할 후 맨 뒤 리프 |
| fallback shelf | shelf별 H 컷 → 그 안에서 V 컷 연쇄 (이미 이 모양 — tree로 자연 변환) |

### 2.5 anchor 백트래킹 재정의

현재 `_allocate_anchor_backtrack`([605](../src/woodcut/strategies/region_based.py:605))은 "앵커 높이로 row를 만들고 호환 그룹을 옆으로 덧댐"이다. tree 관점으로 번역:

- **루트 레벨**: H 컷으로 "이번에 만들 row 높이" 떼어냄.
- **row 레벨**: V 컷 연쇄로 그룹들을 옆으로 배치.
- **그룹 레벨**: 그룹 특성(stacked? 가로?)에 따라 H 혹은 V 연쇄.
- 남은 미사용 그룹 + 남은 리프에 대해 재귀.

백트래킹 탐색은 그대로 유지 — 달라지는 건 "상태를 regions 리스트가 아니라 GNode 트리로 들고 있다".

## 3. 변경 대상

| 파일 | 변경 | 분량 |
|---|---|---|
| `src/woodcut/strategies/gnode.py` (신규) | `GNode` dataclass + `emit_cuts` + invariant 체크 | ~80 라인 |
| `src/woodcut/strategies/region_based.py` | `_pack_multi_group_region` (728-1144) 삭제, tree builder로 대체 | -417 / +200 |
| 동 | `_allocate_anchor_backtrack` (605-726) 리팩토링 — 반환형 regions[] → root GNode | 수정 |
| 동 | `_build_plate_from_regions` (174-245) 간소화 — priority 정렬/dedup 제거, tree 전위 순회로 교체 | -60 / +20 |
| 동 | `_emit_fallback_cuts` (344-392) tree로 재구성 — shelf → H+V 연쇄 | 수정 |
| 동 | `_pack_fallback_shelf` (247-336) 반환형 조정 | 수정 |
| 동 | dead code 의심 영역 (1631-2571) — 호출 여부 확인 후 별도 PR에서 정리 | 본 PR에선 건드리지 않음 |
| `tests/` 또는 CLI 스모크 | 재현 케이스 + baseline + hyuptag + 009/010 회귀 | 보강 |
| `AGENTS.md` | "자주 하는 실수"에 priority 기반 cut emit 금지 한 줄 추가 | 한 줄 |
| `PLAN.md` | 2-Phase Cutting 설명을 tree 기반으로 교체 | 단락 하나 |

## 4. 재사용

- Phase B occupancy(006)의 `Rect`/`intersects` — 배치 가능 여부 판정에 그대로 사용.
- fallback shelf packer(007) 로직 — tree로 변환만.
- 008에서 예정된 partial-count variant — 트리 빌드 단계에서 anchor 선택 시 k 격자로 시도. 008과 **독립 구현 가능**.
- 009/010이 패치한 범위 로직은 **불필요해져 삭제**.

## 5. 검증 계획

### 수치 검증
- 재현 케이스 (2440×1220×2 / 2000×280×4 + 760×260×14 + 100×764×2, 회전 불허):
  - 배치 수 ≥ 기존(18) 유지.
  - placed_w/h 원본 크기와 일치 (±1mm).
  - cut list에 **중복 없음** (dedup 없이도 자연히).
- baseline 11조각, hyuptag preset 모두 배치.

### Guillotine 불변식 자동 검증
- 새 유틸 `validate_guillotine(root) -> bool`:
  - 각 internal 노드의 cut이 노드 직사각형 전체 관통.
  - first/second가 cut 기준으로 정확히 양분 (kerf 포함).
  - 모든 leaf의 piece 경계가 leaf 직사각형 안.
- 재현 + baseline + hyuptag에서 `assert validate_guillotine(root)`.

### 시각적 검증
- Sheet 1 PNG: 007번 발견된 100×764 가로지르기 없음, 010번 발견된 H764 누락 없음.
- 숫자(order) 순서가 Guillotine 실행 순서와 동일 (tree 전위 순회).

### 회귀 테스트
- 회전 허용/불허 baseline 11조각.
- 협탁 preset.
- solution 004 멀티 stock.
- solution 005 stock shortage.
- solution 007 fallback 정확성.
- solution 009 bound.
- solution 010 column_top.

### 제약 조건
- Guillotine: tree 불변식으로 자동 보장.
- kerf 5mm: 자식 노드 생성 시 `kerf` 감산.
- ±1mm 허용 오차: 조각 리프 할당 시 적용.

### 엣지 케이스
- 단일 조각 plate — tree 깊이 1.
- 조각 없음 — 루트 = 스크랩 리프.
- 모든 조각 회전 동일 — V 연쇄 깊이 = count.
- partial packing → 스크랩 리프 다수.

### 성능
- tree builder는 기존 백트래킹 재사용 → 복잡도 동일.
- cut emit는 O(노드 수) = O(조각 수) — 기존 sort O(n log n)보다 빠름.

## 6. 알려진 한계 / 스코프 밖

- 008 (partial-count stacking) 은 tree builder 내부의 "anchor 선택 로직" 문제 — 이 리팩토링 **후에** 붙이는 게 안전. 011은 008을 포함하지 않음.
- [region_based.py:1631-2571](../src/woodcut/strategies/region_based.py:1631) 의 dead-like 코드는 본 PR 스코프 밖. 사용 여부 확인 후 별도 정리.
- 웹 UI는 symlink로 동기화 — 자동.

## 7. 구현 순서

- [ ] 11-1. `strategies/gnode.py` 신설: GNode, emit_cuts, validate_guillotine.
- [ ] 11-2. GNode 단위 smoke (수동 트리 만들어 cut/validate 통과).
- [ ] 11-3. `_pack_fallback_shelf`를 tree로 변환 (가장 단순한 경로로 먼저).
- [ ] 11-4. fallback 포함 재현 케이스 수치 통과.
- [ ] 11-5. `_pack_multi_group_region` tree builder 작성 (anchor row → V 연쇄 → 그룹별 내부 split).
- [ ] 11-6. `_allocate_anchor_backtrack` 반환형을 root GNode로 전환.
- [ ] 11-7. `_build_plate_from_regions` 대체: tree 순회로 cut 리스트 생성.
- [ ] 11-8. 009/010에서 추가한 type별 분기 삭제 (column_top_trim, secondary_row_trim 등). dedup 코드도 삭제.
- [ ] 11-9. 재현 + baseline + hyuptag + 004 + 005 + 009 + 010 회귀 통과.
- [ ] 11-10. `validate_guillotine` 호출을 디버그 assertion으로 포함.
- [ ] 11-11. AGENTS.md / PLAN.md 업데이트.
- [ ] 11-12. 커밋: `refactor(packer): unify region split and cut emit via Guillotine tree`.

## 8. 실제 구현 차이 (2026-04-22)

플랜과 실제 구현이 달라진 지점:

1. **`_pack_multi_group_region`은 배치-only 함수로 축소** (2026-04-22 추가 정리). 초기 커밋에서는 417→~370 라인 함수가 dict cut 생성 코드와 공존했으나, 모든 comprehensive 케이스에서 `_build_region_subtree` 흡수율이 100%(19/19)임을 확인한 뒤 dict cut 블록 전체를 제거했다. 결과: `(placed, cuts)` 튜플 반환 → `list[dict] | None` 반환, ~260 라인 삭제.
   - `tier_boundary`, `region_trim`, `secondary_row_trim`, `column_top_trim`, `stacked_separation`, `piece_separation`, `group_boundary`, `right_trim`, `group_trim` 관련 dict 생성 로직 전부 삭제.
   - 호출부(`_build_plate_from_regions`)도 `all_cuts` 누적·fallback 병합·dedup 전부 제거, `tree_cuts = emit_cuts(plate_root)` 한 줄로 단순화.
   - `_build_region_subtree` 실패는 이제 `AssertionError` — silent dict fallback 없음 (현재 알려진 실패 케이스 0건).

2. **tree 빌드 주체는 `_build_plate_from_regions`**. plate-level skeleton(H 연쇄로 region 경계) + 각 region 내부 재귀 분해를 여기서 한꺼번에 처리. `_allocate_anchor_backtrack` 반환형(regions 리스트)은 유지 — plate dict 조립 단계에서만 tree로 변환된다.

3. **재귀 partitioning 알고리즘** (구현 핵심):
   - pieces 중 x_end 값을 V cut 후보, y_end 값을 H cut 후보로 취함.
   - 각 후보에 대해 "왼쪽/오른쪽(또는 위/아래) 그룹으로 정확히 분리 가능 + 간격 == kerf" 확인.
   - 통과하면 `split_v`/`split_h` 실행 후 양쪽 자식에 재귀.
   - 피스가 1개 남은 leaf는 우측/상단 여백을 V/H scrap split으로 분리.
   - 어떤 split도 안 되는 복잡 케이스(비-guillotine 배치)는 False 반환 → `_build_plate_from_regions`가 `AssertionError`로 실패.

4. **priority / sort_key / dedup 완전 삭제**. tree emit은 전위 순회라 중복·순서 문제가 자료구조적으로 없다. fallback은 이제 아예 없다 — plate cut은 `emit_cuts(plate_root)` 하나의 소스로부터만 나온다.

5. **`validate_guillotine` assertion**: `_build_plate_from_regions` 끝에서 `plate_root`에 대해 호출. 디버그 모드 외 런타임 부하 없음.

6. **`_emit_fallback_shelf` kerf edge 버그 수정** (2026-04-22): shelf 마지막 조각 우측 여분이 kerf 이하일 때 `split_v(right=0)`가 `ValueError`로 터지는 문제 발견. `right_edge >= inner.x2 - 1` → `right_edge + self.kerf >= inner.x2`로 교정. `test_mixed_inventory_uses_both_stocks`가 이 케이스를 커버.

7. **수치**: `tests/test_comprehensive_validation.py` 기준 Guillotine 순서 위반 **173 → 0** (validator kerf 인식 + tree 흡수). pytest 전체 스위트 23/23 통과. 모든 케이스에서 `_build_region_subtree` 성공률 100% (19/19).

## 9. 오픈 질문

1. **기존 regions[] 스키마에 의존하는 visualizer/웹 UI 필드**(`region_x`, `region_y`, `region_w`, `region_h` 등)는 tree 기반에서도 동일하게 채워 호환. visualizer 수정 불필요한지 최종 확인 필요.
2. fallback이 Phase A 실패 시에만 발동하는 구조는 유지. 다만 fallback 트리 루트와 Phase A 트리 루트가 같은 GNode 타입이라 `_pack_single_plate` 반환이 균일해짐.
3. dead code 의심 구역([1631-2571](../src/woodcut/strategies/region_based.py:1631)) 실제 호출 경로 확인 — 호출 안 되면 011에 포함해 삭제할지 여부.
