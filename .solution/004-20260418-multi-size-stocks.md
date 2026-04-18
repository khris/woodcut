# 멀티 사이즈 원판 지원 — 디자인 스펙

- **작성일**: 2026-04-18
- **작성자**: Hong Segi (khris@khrislog.net) + Claude
- **상태**: 승인됨 (사용자 승인 2026-04-18)

## 1. 배경과 목표

### 배경

현재 woodcut은 단일 크기의 원판을 무제한 공급받는 모델이다. 실제 목공 현장은 다르다:

- 사용자는 규격이 다른 원판을 **각각 몇 장씩** 재고로 보유
- 제재목을 사 온 경우 특히 치수가 제각각
- 주류 cutting optimizer 일부는 멀티 사이즈를 지원 ([CutOptim](https://cutoptim.com/calculators/board-cutting-calculator/), [CutList Optimizer](https://www.cutlistoptimizer.com/) 등)

(참고: 자동 집성 기능은 `project_scope_auto_gluing.md` 메모리에 따라 스코프 제외. 사용자가 직접 집성한 결과 판재를 stock으로 입력하는 워크플로우만 지원.)

### 목표

- 서로 다른 규격의 원판을 각기 정해진 수량만큼 보유한 상태에서 최적 재단 계획 생성
- **원판 총 사용 매수 최소화** 를 최우선 지표로 (utilization은 2차)
- 단일 원판 모델은 특수 케이스(`[(W, H, 1)]`)로 자연스럽게 포함

### 비목표 (Non-Goals)

- 자동 집성 기능 (스코프 제외)
- 원판 cost 기반 최적화 (수량만 관리)
- 원판별 회전/결 방향 개별 설정 — 모든 원판이 동일한 `allow_rotation` 규칙 공유

## 2. 주요 변경

### 2.1 입력 모델

```python
# (width, height, count) — count는 반드시 양의 정수
stocks: list[tuple[int, int, int]] = [
    (2440, 1220, 3),   # 2440×1220 원판 3장 보유
    (1800, 900, 2),    # 1800×900 원판 2장 보유
]
```

- `count` 필수 (1 이상). 무제한(`None`) 개념 제거.
- 단일 원판 하위호환 제거. 한 종류여도 `[(2440, 1220, 1)]` 형식.
- 최소 1개의 stock 필수.

### 2.2 알고리즘: Best-Fit Lookahead + 판 수 최소화 편향

**Per-iteration 선택 규칙**

1. 사용 가능한(`count > 0`) 각 stock에 대해 **1장 시뮬레이션 패킹** 실행
2. 각 후보의 `(pieces_placed, utilization)` 수집
3. **사전식(lexicographic) 비교**로 최고 후보 선택:
   - 1차: `pieces_placed` 내림차순 — **가장 많이 흡수하는 원판 우선**
   - 2차: `utilization` 내림차순 — 동수일 때 빽빽한 쪽
   - 3차: 입력 순서 — 동일할 때 사용자 선호
4. 선택된 stock의 count 차감, 해당 조각들 제거, 다음 iteration

**의사코드**

```python
while remaining_pieces and any(s.count > 0 for s in stocks):
    candidates = []
    for stock in stocks:
        if stock.count == 0:
            continue
        trial = simulate_pack_single(stock.width, stock.height, remaining_pieces)
        candidates.append((len(trial.pieces), trial.utilization, stock, trial))
    if not candidates:
        break
    _, _, best_stock, best_plate = max(
        candidates,
        key=lambda c: (c[0], c[1])  # pieces_placed, utilization
    )
    plates.append(best_plate)
    remaining_pieces -= best_plate.pieces
    best_stock.count -= 1
```

**편향의 의미**

순수 utilization 기반은 역설적으로 판 수를 증가시킬 수 있다. 작은 stock에 빽빽이 채우는 쪽이 점수가 높아지기 때문. `pieces_placed`를 1차 키로 두면 "한 판에 최대한 소화하고 끝내자"는 실무 직관과 일치.

### 2.3 복잡도

- 매 iteration마다 사용 가능한 stock 종류 수 `k`만큼 패킹 시뮬레이션 재실행
- 총 이터레이션 수는 최종 사용 원판 수 `P`
- 시뮬레이션당 비용은 기존 단일 원판 패킹과 동일
- **오버헤드 배수: 약 `k`배**
- 조각 50개, stock 종류 3개 기준 기존 대비 ~3배 느려짐
- AGENTS.md의 "정확성 > 성능" 원칙에 따라 수용

## 3. API / UI 변경

### 3.1 Pydantic 모델 (웹 API)

```python
class StockInput(BaseModel):
    width: int
    height: int
    count: int  # >= 1

class CuttingRequest(BaseModel):
    stocks: list[StockInput]  # len >= 1
    kerf: int = 5
    allow_rotation: bool = True
    strategy: str = "region_based"
    pieces: list[PieceInput]
    # 제거: plate_width, plate_height
```

### 3.2 CLI (`interactive.py`)

조각 입력과 동일한 패턴의 루프:

```
원판 1 너비 (mm): 2440
원판 1 높이 (mm): 1220
원판 1 수량: 3
원판 2 너비 (mm, 종료는 0): 1800
원판 2 높이 (mm): 900
원판 2 수량: 2
원판 3 너비 (mm, 종료는 0): 0
✓ 총 원판 5장 (2440×1220 3장, 1800×900 2장)
```

최소 1개 필수.

### 3.3 Web UI (`static/index.html`, `app.js`)

- 원판 섹션을 조각 섹션과 동일한 반복 행 리스트로
- "원판 추가" 버튼, 행별 삭제 버튼
- 각 행: width / height / count

## 4. 코드 변경 지점

| 파일 | 변경 내용 |
|---|---|
| `src/woodcut/packing.py` | `PackingStrategy.__init__` 시그니처를 `stocks: list[tuple[int,int,int]]` 받도록 변경. `plate_width/plate_height`는 현재 선택된 stock의 값을 반영하는 인스턴스 변수로 유지(각 iteration마다 갱신). |
| `src/woodcut/strategies/region_based.py` | `pack()` 내부 while 루프에 stock 선택 로직 삽입. 1장 시뮬레이션용 헬퍼 `_try_pack_single_plate(width, height, pieces)` 추출. |
| `src/woodcut/strategies/region_based_split.py` | 동일한 변경 (동일 부모 클래스 기반). |
| `src/woodcut/web_app/server.py` | `StockInput` 모델 추가, `CuttingRequest`에서 `plate_width/plate_height` 제거 및 `stocks` 추가. `/api/cut` 핸들러에서 stocks 전달. |
| `src/woodcut/interactive.py` | 원판 입력을 루프화. 단일 원판 입력 프롬프트 제거. |
| `src/woodcut/web_app/static/index.html` | 원판 섹션을 동적 리스트로 변경 (현 `plateWidth`/`plateHeight` 단일 input 제거). |
| `src/woodcut/web_app/static/app.js` | 원판 입력 상태 관리 + 추가/삭제 핸들러. Pyodide globals: 현재 `plate_width`/`plate_height` 개별 set → `stocks` 리스트 하나로 set. 새 시그니처에 맞춰 Python 호출부 갱신. |
| `src/woodcut/web_app/static/region_based.py`, `packing.py`, `region_based_split.py` | **자동 복사본** (GitHub Actions + `scripts/extract_web_dependencies.py`가 서버측 파일을 복사). 수동 편집 불필요 — 서버측만 고치면 됨. 단, 로컬 개발 시 동기화 상태 확인 권장. |
| `src/woodcut/visualizer.py` | 판별로 실제 dimension을 사용하도록 수정 (plate dict에 `width`/`height` 포함 필요). |

## 5. 데이터 구조 변경

### Plate dict에 원판 크기 포함

기존 plate dict는 `{'pieces': [...], 'cuts': [...]}` 구조. 이제 각 판이 다른 크기를 가질 수 있으므로:

```python
plate = {
    'width': 2440,       # 신규: 이 판의 원판 너비
    'height': 1220,      # 신규: 이 판의 원판 높이
    'pieces': [...],
    'cuts': [...],
    # (내부 free_spaces는 pack() 종료 후 유지 필요 시)
}
```

시각화, API 응답, 검증 로직 모두 이 정보를 사용.

## 6. 검증 계획 (AGENTS.md 체크리스트 적용)

### 6.1 수치 검증

- 각 케이스별 `placed_pieces == total_pieces` (또는 미배치 조각 명시)
- 사용된 원판 수가 예상 범위 내

### 6.2 시각적 검증

- 각 판이 해당 stock dimension으로 렌더링되는지
- 절단선이 판 경계 내에 있는지

### 6.3 회귀 테스트

- **협탁 테스트 케이스** (`project_test_case_hyuptag.md` 메모리):
  - `stocks=[(2440, 1220, 10)]`, `allow_rotation=False`
  - 기존 결과와 동일한 조각 배치, 동일한 판 수
- 회전 허용/불허 양쪽 테스트

### 6.4 신규 케이스

- **혼합 재고**: `stocks=[(2440,1220,2), (1000,600,3)]`, 다양한 조각 혼합
  - 큰 조각이 큰 원판으로, 작은 조각이 작은 원판으로 분배되는지 (자연 발생 검증)

### 6.5 편향 검증 (핵심)

- **"한 판 완결" 케이스**: 모든 조각이 한 장의 2440×1220에 들어가는 입력 + 추가 stock `(1000,600,5)`
  - **예상**: 2440×1220 1장만 사용, 1000×600은 소모하지 **않음**
  - 순수 utilization B라면 작은 원판을 선택할 수 있는 상황

### 6.6 엣지 케이스

- Stock 고갈: 배치 불가 조각 리스트를 명시 리포트, 예외 아님
- 어떤 stock에도 못 들어가는 조각: 조기 명시적 에러
- 회전 불허 + 세로로 긴 조각 + stock 중 세로가 부족: 회전 없이 다른 stock 시도

### 6.7 제약 조건

- Guillotine cut 제약 유지
- Kerf 고려 유지
- 조각 치수 정확성(±1mm)

## 7. 알려진 한계 / 트레이드오프

- **탐욕(greedy)**: per-iteration 최선이 전역 최선이 아닐 수 있음. 예: 첫 판에서 조각 10개를 흡수하는 큰 stock을 선택했지만, 그 stock을 둘째 판용으로 아꼈으면 전체 판 수가 더 적어질 수 있는 시나리오. 현 단계에서는 수용.
- **성능 배수 k**: stock 종류가 많으면 선형 증가. 실무 시나리오에서 k는 보통 2–5이므로 문제 없음 예상.
- **시뮬레이션 결과 재사용 없음**: 매 iteration마다 모든 후보를 처음부터 시뮬레이션. 캐싱은 향후 최적화 대상.

## 8. 마이그레이션

- 단일 원판 하위호환 제거: 기존 API 클라이언트는 업데이트 필요.
- CLI/Web UI 모두 사용자 입력 방식 변경 — 사용자에게 명확한 안내 필요.
- 기존 테스트/스크립트의 호출 형태를 새 시그니처로 일괄 수정.

## 9. 구현 순서 제안 (writing-plans에서 상세화)

1. `PackingStrategy` 시그니처 변경 및 `_try_pack_single_plate` 추출
2. `RegionBasedPacker.pack()` 멀티 stock 루프로 재작성 + 선택 로직
3. `region_based_split` 동일 변경
4. Plate dict에 width/height 추가 → visualizer 반영
5. CLI 원판 입력 루프화
6. Web API 모델 변경
7. Web UI 원판 섹션 동적 리스트화
8. 회귀/신규/편향/엣지 테스트 케이스 실행 및 검증
