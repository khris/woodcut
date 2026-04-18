# 멀티 사이즈 원판 지원 — 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 서로 다른 규격의 원판을 각 수량만큼 보유한 상태에서, Best-Fit Lookahead + 판 수 최소화 편향 알고리즘으로 재단을 계획한다.

**Architecture:** 기존 `RegionBasedPacker.pack()`의 단일 플레이트 루프 본체를 `_pack_single_plate()` 헬퍼로 추출 후, 그 위에 멀티 stock 선택 루프를 씌운다. Stock 선택은 각 후보에 시뮬레이션 패킹을 돌려 `(pieces_placed, utilization)` 사전식 비교.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, matplotlib, Pyodide, uv.

**Spec 참조:** `.solution/004-20260418-multi-size-stocks.md`

---

## 파일 구조

### 새로 생성

- `tests/__init__.py` — 빈 파일
- `tests/test_stock_selector.py` — stock 선택 로직 단위 테스트
- `tests/test_multi_stock_integration.py` — 엔드투엔드 회귀/신규/편향/엣지 케이스

### 수정

- `pyproject.toml` — pytest 추가
- `src/woodcut/packing.py` — `PackingStrategy.__init__` 시그니처 변경 (`stocks` 인자)
- `src/woodcut/strategies/region_based.py` — `_pack_single_plate` 추출, 멀티 stock 루프, stock 선택 로직
- `src/woodcut/strategies/region_based_split.py` — 부모 변경 반영 (대부분 자동 계승)
- `src/woodcut/visualizer.py` — 판별 dimension 사용
- `src/woodcut/interactive.py` — 원판 입력 루프화
- `src/woodcut/web_app/server.py` — Pydantic 모델 (`StockInput`)
- `src/woodcut/web_app/static/index.html` — 원판 섹션 동적 리스트
- `src/woodcut/web_app/static/app.js` — 원판 상태 관리, Pyodide globals 변경

---

## Phase 1: 알고리즘 코어

### Task 1: pytest 환경 셋업

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: `pyproject.toml`의 dev dependencies에 pytest 추가**

`pyproject.toml` 수정 — `[dependency-groups]` 블록 교체:

```toml
[dependency-groups]
dev = [
    "ruff>=0.14.10",
    "pytest>=8.0.0",
]
```

- [ ] **Step 2: tests 디렉토리 생성 및 smoke test**

Create `tests/__init__.py` (빈 파일)

Create `tests/test_smoke.py`:

```python
def test_pytest_runs():
    assert 1 + 1 == 2
```

- [ ] **Step 3: 설치 및 smoke test 실행**

```bash
uv sync
uv run pytest tests/test_smoke.py -v
```

Expected: `1 passed`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock tests/__init__.py tests/test_smoke.py
git commit -m "chore: add pytest for multi-stock test coverage"
```

---

### Task 2: Stock 선택 로직 단위 테스트 (FAIL 먼저)

**Files:**
- Create: `tests/test_stock_selector.py`

- [ ] **Step 1: 실패할 테스트 작성**

Create `tests/test_stock_selector.py`:

```python
"""Stock 선택 로직 단위 테스트

select_best_stock: 후보 중 (pieces_placed, utilization) 사전식 최고를 선택.
Lookahead 시뮬레이션 결과를 입력으로 받음 (실제 packing은 mocking).
"""
from woodcut.strategies.region_based import select_best_stock


def test_selects_stock_with_most_pieces_placed():
    """조각 수 많은 쪽이 utilization 낮아도 우선."""
    # 후보: (stock_index, pieces_placed, utilization)
    candidates = [
        (0, 3, 0.9),   # 작은 원판, 빽빽하지만 3개만
        (1, 7, 0.5),   # 큰 원판, 엉성하지만 7개 흡수
    ]
    assert select_best_stock(candidates) == 1


def test_utilization_is_tiebreaker():
    """조각 수 같으면 utilization 높은 쪽."""
    candidates = [
        (0, 5, 0.7),
        (1, 5, 0.9),
        (2, 5, 0.6),
    ]
    assert select_best_stock(candidates) == 1


def test_input_order_is_final_tiebreaker():
    """조각 수도 utilization도 같으면 입력 순서(첫번째) 선택."""
    candidates = [
        (0, 5, 0.8),
        (1, 5, 0.8),
        (2, 5, 0.8),
    ]
    assert select_best_stock(candidates) == 0


def test_empty_candidates_returns_none():
    """후보 없으면 None."""
    assert select_best_stock([]) is None


def test_single_candidate():
    """후보 하나면 그것."""
    assert select_best_stock([(0, 5, 0.7)]) == 0
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
uv run pytest tests/test_stock_selector.py -v
```

Expected: FAIL with `ImportError: cannot import name 'select_best_stock'`

- [ ] **Step 3: 커밋하지 않고 다음 태스크로** (RED 상태 유지)

---

### Task 3: `select_best_stock` 구현 (GREEN)

**Files:**
- Modify: `src/woodcut/strategies/region_based.py` (파일 상단 helper로 추가)

- [ ] **Step 1: Helper 함수 추가**

Insert near the top of `src/woodcut/strategies/region_based.py` (import 다음, class 정의 이전):

```python
def select_best_stock(
    candidates: list[tuple[int, int, float]]
) -> int | None:
    """사전식 비교로 최적 stock index 선택.

    Args:
        candidates: [(stock_index, pieces_placed, utilization), ...]

    Returns:
        최고 후보의 stock_index, 후보 없으면 None.

    규칙:
        1차: pieces_placed 내림차순
        2차: utilization 내림차순
        3차: 입력 순서(작은 index) — max가 후행 동점을 덮어쓰지 않게 처리
    """
    if not candidates:
        return None

    # max()는 동점 시 앞의 것을 유지 — (pieces, util) 역순 비교로 OK
    best = max(candidates, key=lambda c: (c[1], c[2]))
    return best[0]
```

- [ ] **Step 2: 테스트 실행 (통과 확인)**

```bash
uv run pytest tests/test_stock_selector.py -v
```

Expected: `5 passed`

- [ ] **Step 3: Commit**

```bash
git add src/woodcut/strategies/region_based.py tests/test_stock_selector.py
git commit -m "feat: add stock selection helper with lexicographic ordering"
```

---

### Task 4: `PackingStrategy.__init__` 시그니처 변경

**Files:**
- Modify: `src/woodcut/packing.py:37-41`

- [ ] **Step 1: 베이스 클래스 생성자 수정**

Replace `PackingStrategy.__init__` in `src/woodcut/packing.py`:

```python
    def __init__(
        self,
        stocks: list[tuple[int, int, int]],
        kerf: int = 5,
        allow_rotation: bool = True,
    ) -> None:
        """
        Args:
            stocks: [(width, height, count), ...] — 보유 원판 목록, count >= 1
            kerf: 톱날 두께
            allow_rotation: 조각 회전 허용 여부
        """
        if not stocks:
            raise ValueError("stocks는 최소 1개 필요")
        for w, h, c in stocks:
            if w <= 0 or h <= 0 or c <= 0:
                raise ValueError(f"stock ({w}, {h}, {c}): 모든 값은 양수여야 함")

        self.stocks: list[tuple[int, int, int]] = stocks
        # 현재 작업 중인 원판 크기 — pack() 내부에서 매 iteration 갱신
        self.plate_width: int = stocks[0][0]
        self.plate_height: int = stocks[0][1]
        self.kerf: int = kerf
        self.allow_rotation: bool = allow_rotation
```

- [ ] **Step 2: 단위 검증**

```bash
uv run python -c "from woodcut.packing import PackingStrategy; print('OK')"
```

Expected: `OK`

단일 원판 호환은 **제거** — 기존 사용처는 Task 5-11에서 모두 새 시그니처로 업데이트.

- [ ] **Step 3: Commit (다음 태스크와 함께)** — 스킵, Task 5에서 한 번에.

---

### Task 5: `_pack_single_plate` 추출 + 멀티 stock 루프

**Files:**
- Modify: `src/woodcut/strategies/region_based.py` (`pack()` 전면 재작성, 라인 27-178)

이 태스크는 기존 while 루프 본체를 `_pack_single_plate(remaining_pieces)` 메서드로 뽑고, 그 위에 멀티 stock 루프를 씌운다.

- [ ] **Step 1: `_pack_single_plate` 메서드 추가**

`RegionBasedPacker` 클래스 안에 추가 (기존 `pack()` 뒤에 배치):

```python
    def _pack_single_plate(self, remaining_pieces: list[dict]) -> dict:
        """현재 self.plate_width/height 기준으로 원판 1장 패킹.

        호출 측에서 self.plate_width/height를 사전에 세팅해야 함.
        remaining_pieces는 수정하지 않음 — 반환된 plate['pieces']로 호출자가 차감.

        Returns:
            plate dict: {'width', 'height', 'pieces', 'cuts', 'free_spaces'}
        """
        # 1. 레벨 1: 정확히 같은 크기끼리 그룹화
        groups = self._group_by_exact_size(remaining_pieces)

        # 2. 각 그룹의 회전 옵션 생성
        group_options = self._generate_group_options(groups)

        # 3. 회전 옵션 평면화
        all_variants = self._flatten_group_options(group_options)

        # 4. 앵커 기반 백트래킹으로 최적 조합 찾기
        regions = self._allocate_anchor_backtrack(all_variants)

        # 영역 간 trim 최적화
        if regions:
            self._optimize_trim_placement(regions)

        # 폴백 판단
        if not regions:
            plate = {
                'width': self.plate_width,
                'height': self.plate_height,
                'pieces': [],
                'cuts': [],
                'free_spaces': [FreeSpace(0, 0, self.plate_width, self.plate_height)],
            }
            for piece in remaining_pieces:
                placement = self._find_best_placement_simple(
                    plate['free_spaces'], plate['pieces'], piece
                )
                if placement:
                    self._apply_placement(
                        plate['free_spaces'], plate['pieces'], piece, placement
                    )
            self.generate_guillotine_cuts(plate)
            return plate

        # 일반 배치
        plate = {
            'width': self.plate_width,
            'height': self.plate_height,
            'pieces': [],
            'cuts': [],
            'free_spaces': [],
        }

        for i, region in enumerate(regions):
            region['id'] = f'R{i+1}'

        all_cuts = []
        for i, region in enumerate(regions):
            placed, cuts = self._pack_multi_group_region(
                region,
                region['id'],
                region_index=i,
                is_first_region=(i == 0),
                is_last_region=(i == len(regions) - 1),
                region_priority_base=i * 100,
            )
            if placed:
                plate['pieces'].extend(placed)

            if cuts:
                for cut in cuts:
                    cut['region_index'] = i
                all_cuts.extend(cuts)

        # 절단선 정렬
        def sort_key(cut):
            priority = cut.get('priority', 100)
            region_idx = cut.get('region_index', 0)
            sub_priority = cut.get('sub_priority', 0)
            position = cut.get('position', 0)
            if priority == 1:
                return (priority, position, 0, 0)
            return (priority, region_idx, sub_priority, position)

        all_cuts.sort(key=sort_key)
        for idx, cut in enumerate(all_cuts):
            cut['order'] = idx + 1
            if 'region_x' not in cut:
                cut['region_x'] = 0
                cut['region_y'] = 0
                cut['region_w'] = self.plate_width
                cut['region_h'] = self.plate_height
        plate['cuts'] = all_cuts
        return plate
```

- [ ] **Step 2: `pack()` 전면 재작성 — 멀티 stock 루프**

`pack()` 메서드 전체를 다음으로 교체:

```python
    def pack(self, pieces: list[tuple[int, int, int]]) -> list[dict]:
        """멀티 stock 패킹.

        매 iteration마다:
          1. 각 남은 stock 종류에 대해 1장 시뮬레이션
          2. (pieces_placed, utilization) 사전식 최고 stock 선택
          3. 해당 stock count 차감, 배치된 조각 제거
        """
        all_pieces = self.expand_pieces(pieces)
        plates = []
        remaining_pieces = all_pieces[:]
        # stock count 가변 복사 (원본 self.stocks는 유지)
        stock_counts = [s[2] for s in self.stocks]

        plate_num = 1
        while remaining_pieces and any(c > 0 for c in stock_counts):
            print(f"\n=== 원판 {plate_num}: stock 선택 시뮬레이션 ===")

            # 후보별 시뮬레이션
            candidates = []  # (stock_index, pieces_placed, utilization, plate_dict)
            for i, (w, h, _count) in enumerate(self.stocks):
                if stock_counts[i] == 0:
                    continue
                self.plate_width = w
                self.plate_height = h
                trial = self._pack_single_plate(remaining_pieces)
                placed = len(trial['pieces'])
                total_placed_area = sum(
                    p.get('placed_w', p['width']) * p.get('placed_h', p['height'])
                    for p in trial['pieces']
                )
                util = total_placed_area / (w * h) if w * h else 0.0
                candidates.append((i, placed, util, trial))
                print(f"  후보 {i}: {w}×{h} → {placed}개, util={util:.2%}")

            if not candidates:
                print("⚠️  사용 가능 stock 없음")
                break

            scored = [(c[0], c[1], c[2]) for c in candidates]
            best_idx = select_best_stock(scored)
            best_candidate = next(c for c in candidates if c[0] == best_idx)
            _, best_placed, best_util, best_plate = best_candidate
            best_w, best_h, _ = self.stocks[best_idx]

            if best_placed == 0:
                print("⚠️  어느 stock에도 배치 실패 — 종료")
                break

            print(
                f"✓ 선택: stock[{best_idx}] {best_w}×{best_h} "
                f"({best_placed}개, {best_util:.2%})"
            )

            plates.append(best_plate)
            stock_counts[best_idx] -= 1

            # 배치된 조각을 remaining에서 제거
            placed_sizes = {}
            for p in best_plate['pieces']:
                size_key = (p['width'], p['height'])
                placed_sizes[size_key] = placed_sizes.get(size_key, 0) + 1

            new_remaining = []
            for piece in remaining_pieces:
                size_key = (piece['width'], piece['height'])
                if size_key in placed_sizes and placed_sizes[size_key] > 0:
                    placed_sizes[size_key] -= 1
                else:
                    new_remaining.append(piece)
            remaining_pieces = new_remaining

            plate_num += 1

        if remaining_pieces:
            print(f"\n⚠️  미배치 조각 {len(remaining_pieces)}개 — stock 부족 또는 크기 초과")

        return plates
```

- [ ] **Step 3: 단일 stock 스모크 테스트**

```bash
uv run python -c "
from woodcut.strategies.region_based import RegionBasedPacker
packer = RegionBasedPacker([(2440, 1220, 2)], kerf=5, allow_rotation=True)
plates = packer.pack([(800, 310, 2), (644, 310, 3), (371, 270, 4)])
print(f'Plates: {len(plates)}')
print(f'Placed: {sum(len(p[\"pieces\"]) for p in plates)}')
assert all('width' in p and 'height' in p for p in plates), 'plate missing dimensions'
print('OK')
"
```

Expected: `Plates: 1`, `Placed: 9`, `OK` (기존 케이스 한 판에 9개 배치)

- [ ] **Step 4: Commit**

```bash
git add src/woodcut/packing.py src/woodcut/strategies/region_based.py
git commit -m "feat: multi-stock packing with best-fit lookahead selection"
```

---

### Task 6: `RegionBasedPackerWithSplit` 호환성 확인

**Files:**
- Modify: `src/woodcut/strategies/region_based_split.py` (필요 시)

- [ ] **Step 1: 파일 확인**

```bash
uv run python -c "
from woodcut.strategies.region_based_split import RegionBasedPackerWithSplit
packer = RegionBasedPackerWithSplit([(2440, 1220, 2)], kerf=5, allow_rotation=True)
plates = packer.pack([(800, 310, 2), (644, 310, 3)])
print(f'Plates: {len(plates)}, Placed: {sum(len(p[\"pieces\"]) for p in plates)}')
print('OK')
"
```

Expected: `OK` (부모 클래스 변경이 자동 계승되면 통과)

- [ ] **Step 2: 실패 시 `__init__` 수정**

만약 `region_based_split.py`가 자체 `__init__`을 가졌다면 동일 시그니처로 맞춤:

```python
    def __init__(
        self,
        stocks: list[tuple[int, int, int]],
        kerf: int = 5,
        allow_rotation: bool = True,
    ) -> None:
        super().__init__(stocks, kerf, allow_rotation)
```

- [ ] **Step 3: Commit (필요 시)**

```bash
git add src/woodcut/strategies/region_based_split.py
git commit -m "chore: align RegionBasedPackerWithSplit with new stocks signature"
```

(변경 없으면 스킵)

---

## Phase 2: 표면 레이어

### Task 7: Visualizer — 판별 dimension 사용

**Files:**
- Modify: `src/woodcut/visualizer.py:33-42` (함수 시그니처), 본문 내 `plate_width`/`plate_height` 참조 지점

- [ ] **Step 1: 시그니처 및 사용 지점 수정**

`visualize_solution` 함수 시그니처를 다음으로 변경:

```python
def visualize_solution(plates, pieces, strategy_name="unknown"):
    """시각화 함수

    Args:
        plates: 패킹 결과 — 각 plate에 'width', 'height', 'pieces', 'cuts' 포함
        pieces: 원본 조각 리스트 [(width, height, count), ...]
        strategy_name: 전략 이름 (파일명에 사용)
    """
```

본문에서 `plate_width`, `plate_height` 참조 지점을 각 루프 내 `plate['width']`, `plate['height']`로 교체. figsize 계산 시 판마다 크기가 다르므로 각 ax마다 xlim/ylim을 해당 plate 크기로 설정.

(함수 내부 세부는 호출하는 Axes별로 plate['width']/plate['height']를 사용하도록 수정.)

- [ ] **Step 2: 호출처 업데이트**

`src/woodcut/interactive.py:103`의 `visualize_solution` 호출:

```python
# Before
visualize_solution(plates, pieces, plate_width, plate_height, strategy_name)
# After
visualize_solution(plates, pieces, strategy_name)
```

- [ ] **Step 3: CLI 스모크 테스트**

(Task 8 CLI 루프 완료 후 전체 실행으로 검증 — 여기서는 import만 확인)

```bash
uv run python -c "from woodcut.visualizer import visualize_solution; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/woodcut/visualizer.py src/woodcut/interactive.py
git commit -m "refactor: visualizer reads per-plate dimensions"
```

---

### Task 8: CLI 원판 입력 루프

**Files:**
- Modify: `src/woodcut/interactive.py:40-95`

- [ ] **Step 1: 원판 입력 루프로 교체**

`run_interactive()` 본문에서 단일 원판 입력 (라인 46-54)을 다음으로 교체:

```python
    # 원판 입력 받기
    print("\n[보유 원판 입력]")
    print("입력을 마치려면 너비에 '0' 또는 엔터를 입력하세요. (최소 1개)")
    stocks: list[tuple[int, int, int]] = []
    while True:
        idx = len(stocks) + 1
        w = get_positive_int_input(f"원판 {idx} 너비 (mm, 기본값 2440): ", default=2440 if idx == 1 else None)
        if w is None or w == 0:
            if not stocks:
                print("❌ 오류: 최소 한 개의 원판은 입력해야 합니다.")
                continue
            break

        h = get_positive_int_input(f"원판 {idx} 높이 (mm, 기본값 1220): ", default=1220 if idx == 1 else None)
        if h is None:
            print("❌ 높이 입력을 취소하고 다시 너비부터 입력합니다.")
            continue

        c = get_positive_int_input(f"원판 {idx} 수량 (장, 기본값 1): ", default=1)
        if c is None:
            c = 1

        stocks.append((w, h, c))
        print(f"  + 원판 추가: {w}×{h}mm, {c}장")

    total_plates = sum(s[2] for s in stocks)
    print(f"✓ 총 {len(stocks)}종류, {total_plates}장 원판 보유")
```

그리고 `RegionBasedPacker(plate_width, plate_height, kerf, allow_rotation)` 호출(라인 96)을:

```python
    packer = RegionBasedPacker(stocks, kerf, allow_rotation)
```

- [ ] **Step 2: 통합 스모크 테스트**

```bash
printf "2440\n1220\n2\n0\n5\ny\n800\n310\n2\n644\n310\n3\n371\n270\n4\n0\n" | uv run woodcut
```

Expected: 에러 없이 완료, 출력 파일 생성.

- [ ] **Step 3: Commit**

```bash
git add src/woodcut/interactive.py
git commit -m "feat: CLI prompts for multiple stock sizes with counts"
```

---

### Task 9: Web API Pydantic 모델

**Files:**
- Modify: `src/woodcut/web_app/server.py:30-102`

- [ ] **Step 1: 모델 교체**

`server.py`의 기존 모델 블록을 다음으로 교체:

```python
class PieceInput(BaseModel):
    """조각 입력 모델"""
    width: int
    height: int
    count: int


class StockInput(BaseModel):
    """원판 입력 모델"""
    width: int
    height: int
    count: int


class CuttingRequest(BaseModel):
    """재단 요청 모델"""
    stocks: list[StockInput]
    kerf: int = 5
    allow_rotation: bool = True
    strategy: str = "region_based"
    pieces: list[PieceInput]


class CuttingResponse(BaseModel):
    """재단 응답 모델"""
    success: bool
    total_pieces: int
    placed_pieces: int
    plates_used: int
    plates: list[dict]
```

- [ ] **Step 2: 핸들러 수정**

`calculate_cutting` 핸들러 본문 수정:

```python
@app.post("/api/cut", response_model=CuttingResponse)
async def calculate_cutting(request: CuttingRequest):
    """재단 계획 계산 API"""
    try:
        pieces = [(p.width, p.height, p.count) for p in request.pieces]
        stocks = [(s.width, s.height, s.count) for s in request.stocks]

        if not pieces:
            raise HTTPException(status_code=400, detail="조각 정보가 없습니다")
        if not stocks:
            raise HTTPException(status_code=400, detail="원판 정보가 없습니다")

        if request.strategy == "region_based_split":
            packer = RegionBasedPackerWithSplit(stocks, request.kerf, request.allow_rotation)
        else:
            packer = RegionBasedPacker(stocks, request.kerf, request.allow_rotation)
        plates = packer.pack(pieces)

        total_pieces = sum(p.count for p in request.pieces)
        placed_pieces = sum(len(plate['pieces']) for plate in plates)

        return CuttingResponse(
            success=True,
            total_pieces=total_pieces,
            placed_pieces=placed_pieces,
            plates_used=len(plates),
            plates=plates,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 3: API 스모크 테스트**

```bash
uv run woodcut web &
SERVER_PID=$!
sleep 2
curl -s -X POST http://localhost:8000/api/cut \
  -H "Content-Type: application/json" \
  -d '{
    "stocks": [{"width": 2440, "height": 1220, "count": 1}],
    "kerf": 5,
    "allow_rotation": true,
    "pieces": [{"width": 800, "height": 310, "count": 2}]
  }' | python -m json.tool
kill $SERVER_PID
```

Expected: `"success": true`, `"placed_pieces": 2`, plate에 `width`/`height` 필드 포함.

- [ ] **Step 4: Commit**

```bash
git add src/woodcut/web_app/server.py
git commit -m "feat(api): accept stocks list instead of single plate dimensions"
```

---

### Task 10: Web UI HTML — 원판 섹션 동적 리스트

**Files:**
- Modify: `src/woodcut/web_app/static/index.html` (원판 입력 블록 교체)

- [ ] **Step 1: 원판 입력 영역 교체**

`index.html`의 기존 `<div class="form-group">` (plateWidth, plateHeight) 블록을 찾아 다음으로 교체 — 기존 조각 입력 섹션과 동일한 동적 리스트 패턴 사용:

```html
<div class="panel-section">
    <h3>보유 원판</h3>
    <div id="stocksList"></div>
    <button type="button" id="addStockBtn" class="btn-secondary">+ 원판 추가</button>
</div>
```

조각 섹션의 행 템플릿과 동일 스타일의 row markup을 JS가 삽입하게 한다 (Task 11 참조).

- [ ] **Step 2: 기존 단일 input 제거 확인**

`id="plateWidth"`, `id="plateHeight"` 관련 요소와 그에 연결된 label을 모두 삭제.

- [ ] **Step 3: Commit (Task 11과 함께)** — 스킵.

---

### Task 11: Web UI app.js — stock 상태 관리 및 Pyodide 페이로드

**Files:**
- Modify: `src/woodcut/web_app/static/app.js` (다수 지점)

- [ ] **Step 1: Stock 상태 관리 함수 추가**

`app.js` 상단에 추가 (기존 pieces 관리 코드 패턴과 일관되게):

```javascript
let stocks = [];

function addStockRow(width = 2440, height = 1220, count = 1) {
    const row = {
        id: Date.now() + Math.random(),
        width, height, count
    };
    stocks.push(row);
    renderStocks();
}

function removeStockRow(id) {
    stocks = stocks.filter(s => s.id !== id);
    renderStocks();
}

function renderStocks() {
    const list = document.getElementById('stocksList');
    list.innerHTML = '';
    stocks.forEach(s => {
        const row = document.createElement('div');
        row.className = 'stock-row';
        row.innerHTML = `
            <input type="number" min="1" value="${s.width}" data-field="width" class="stock-input">
            <span>×</span>
            <input type="number" min="1" value="${s.height}" data-field="height" class="stock-input">
            <span>mm</span>
            <input type="number" min="1" value="${s.count}" data-field="count" class="stock-input">
            <span>장</span>
            <button type="button" class="btn-remove" aria-label="삭제">×</button>
        `;
        row.querySelectorAll('.stock-input').forEach(input => {
            input.addEventListener('input', e => {
                s[e.target.dataset.field] = parseInt(e.target.value) || 0;
            });
        });
        row.querySelector('.btn-remove').addEventListener('click', () => removeStockRow(s.id));
        list.appendChild(row);
    });
}

// 페이지 로드 시 기본 원판 하나 표시
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('addStockBtn').addEventListener('click', () => addStockRow());
    addStockRow();  // 기본 1행
});
```

- [ ] **Step 2: Pyodide 호출 페이로드 변경**

`app.js`에서 기존 pyodide 실행 블록 (현재 `plate_width`, `plate_height`를 set하는 라인 250-251 포함 영역)을 다음으로 교체:

```javascript
        // 입력 검증
        if (stocks.length === 0) {
            showStatus('원판을 최소 1개 추가해주세요', 'error');
            return;
        }
        const invalidStock = stocks.find(s => s.width <= 0 || s.height <= 0 || s.count <= 0);
        if (invalidStock) {
            showStatus('원판 치수와 수량은 모두 양수여야 합니다', 'error');
            return;
        }

        // Pyodide에 전달
        pyodide.globals.set('pieces_input', pieces);
        pyodide.globals.set('stocks_input', stocks.map(s => [s.width, s.height, s.count]));
        pyodide.globals.set('kerf', kerf);
        pyodide.globals.set('allow_rotation', allowRotation);

        const packerClass = strategy === 'region_based_split'
            ? 'RegionBasedPackerWithSplit'
            : 'RegionBasedPacker';

        const result = await pyodide.runPythonAsync(`
packer = ${packerClass}(stocks_input, kerf, allow_rotation)
plates = packer.pack(pieces_input)

total_pieces = sum(p[2] for p in pieces_input)
placed_pieces = sum(len(plate['pieces']) for plate in plates)

{
    'success': True,
    'total_pieces': total_pieces,
    'placed_pieces': placed_pieces,
    'plates_used': len(plates),
    'plates': plates
}
        `);
```

- [ ] **Step 3: `displayResult` 및 SVG 렌더링 수정**

`displayResult(data, plateWidth, plateHeight, kerf)` 시그니처를 `displayResult(data, kerf)`로 변경. 각 plate 순회 시 `createPlateSVG(plate, plate.width, plate.height, kerf)`로 plate 자체의 치수 사용:

```javascript
function displayResult(data, kerf) {
    const statsDiv = document.getElementById('resultStats');
    const visualDiv = document.getElementById('visualization');

    const efficiency = (data.placed_pieces / data.total_pieces * 100).toFixed(1);
    statsDiv.innerHTML = `
        <div><strong>총 조각:</strong> ${data.total_pieces}개</div>
        <div><strong>배치 조각:</strong> ${data.placed_pieces}개</div>
        <div><strong>사용 원판:</strong> ${data.plates_used}장</div>
        <div><strong>배치율:</strong> ${efficiency}%</div>
    `;
    visualDiv.innerHTML = '';

    data.plates.forEach((plate, plateIndex) => {
        const svgContainer = document.createElement('div');
        svgContainer.style.marginBottom = '30px';

        const title = document.createElement('h3');
        title.textContent = `원판 ${plateIndex + 1} (${plate.width}×${plate.height}mm)`;
        title.style.textAlign = 'center';
        title.style.marginBottom = '10px';
        svgContainer.appendChild(title);

        const svg = createPlateSVG(plate, plate.width, plate.height, kerf);
        svgContainer.appendChild(svg);
        visualDiv.appendChild(svgContainer);
    });
}
```

그리고 `displayResult(data, plateWidth, plateHeight, kerf)` 호출부를 `displayResult(data, kerf)`로 수정.

- [ ] **Step 4: 스타일 추가 (필요 시)**

`style.css`에 `.stock-row`, `.stock-input`, `.btn-remove` 클래스가 없으면 추가. 기존 조각 행 스타일과 일관성 유지.

- [ ] **Step 5: 브라우저 스모크 테스트**

```bash
uv run woodcut web
```

브라우저에서 `http://localhost:8000` 열고 확인:
- 원판 1행 기본 표시
- "+ 원판 추가" 버튼으로 행 추가 가능
- 삭제 버튼 작동
- 조각 추가 후 "계산" 실행 → 결과 표시
- 각 plate 타이틀에 치수 표시

Expected: 수동 확인 통과.

- [ ] **Step 6: Commit**

```bash
git add src/woodcut/web_app/static/index.html src/woodcut/web_app/static/app.js src/woodcut/web_app/static/style.css
git commit -m "feat(web): multi-stock input UI with dynamic row list"
```

---

## Phase 3: 통합 테스트

### Task 12: 회귀 테스트 — 단일 원판

**Files:**
- Create: `tests/test_multi_stock_integration.py`

- [ ] **Step 1: 회귀 테스트 작성**

Create `tests/test_multi_stock_integration.py`:

```python
"""멀티 stock 통합 테스트 — 회귀/신규/편향/엣지."""
from woodcut.strategies.region_based import RegionBasedPacker


HYUPTAG_PIECES = [
    (560, 350, 2),
    (446, 50, 2),
    (369, 50, 2),
    (550, 450, 1),
    (450, 100, 1),
    (450, 332, 2),
    (450, 278, 1),
]


def test_regression_hyuptag_no_rotation():
    """협탁 테스트 (회전 불허) — 기존 동작 재현."""
    packer = RegionBasedPacker(
        [(2440, 1220, 10)], kerf=5, allow_rotation=False
    )
    plates = packer.pack(HYUPTAG_PIECES)
    placed = sum(len(p['pieces']) for p in plates)
    total = sum(c for _, _, c in HYUPTAG_PIECES)
    assert placed == total, f"{placed}/{total} 배치"


def test_regression_basic_rotation():
    """기본 테스트 케이스 (회전 허용)."""
    packer = RegionBasedPacker(
        [(2440, 1220, 5)], kerf=5, allow_rotation=True
    )
    plates = packer.pack([(800, 310, 2), (644, 310, 3), (371, 270, 4), (369, 640, 2)])
    placed = sum(len(p['pieces']) for p in plates)
    assert placed == 11, f"{placed}/11 배치"


def test_plate_dict_has_dimensions():
    """각 plate에 width/height 포함 확인."""
    packer = RegionBasedPacker(
        [(2440, 1220, 2)], kerf=5, allow_rotation=True
    )
    plates = packer.pack([(800, 310, 2)])
    assert plates, "최소 1장"
    for p in plates:
        assert 'width' in p and 'height' in p
        assert p['width'] == 2440 and p['height'] == 1220
```

- [ ] **Step 2: 실행**

```bash
uv run pytest tests/test_multi_stock_integration.py -v
```

Expected: `3 passed`

- [ ] **Step 3: Commit**

```bash
git add tests/test_multi_stock_integration.py
git commit -m "test: regression for single-stock behavior via new stocks API"
```

---

### Task 13: 혼합 재고 테스트

**Files:**
- Modify: `tests/test_multi_stock_integration.py`

- [ ] **Step 1: 테스트 추가**

Append to `tests/test_multi_stock_integration.py`:

```python
def test_mixed_inventory_uses_both_stocks():
    """혼합 재고: 큰 원판과 작은 원판이 모두 사용되는 케이스."""
    # 큰 원판 1장에 다 안 들어가는 총 면적 + 작은 원판도 보조 필요
    packer = RegionBasedPacker(
        [(2440, 1220, 1), (1000, 600, 3)],
        kerf=5,
        allow_rotation=True,
    )
    # 큰 조각 + 작은 조각 섞어서
    plates = packer.pack([(800, 600, 4), (400, 300, 6)])

    placed = sum(len(p['pieces']) for p in plates)
    assert placed == 10, f"{placed}/10 배치"
    # 최소 2장 사용 (큰 1장만으로는 안 됨)
    assert len(plates) >= 2


def test_stock_count_respected():
    """Stock count를 초과해서 사용하지 않음."""
    packer = RegionBasedPacker(
        [(2440, 1220, 1)],  # 단 1장만
        kerf=5,
        allow_rotation=True,
    )
    # 큰 조각 여러 개 — 한 장에 다 못 들어감
    plates = packer.pack([(2000, 1000, 5)])
    assert len(plates) == 1, f"원판 1장만 사용해야 하는데 {len(plates)}장"
```

- [ ] **Step 2: 실행**

```bash
uv run pytest tests/test_multi_stock_integration.py -v
```

Expected: `5 passed`

- [ ] **Step 3: Commit**

```bash
git add tests/test_multi_stock_integration.py
git commit -m "test: mixed inventory uses multiple stock sizes within count limits"
```

---

### Task 14: 판 수 최소화 편향 검증 (핵심)

**Files:**
- Modify: `tests/test_multi_stock_integration.py`

- [ ] **Step 1: 편향 테스트 추가**

Append:

```python
def test_bias_prefers_one_large_plate_over_many_small():
    """한 장의 큰 원판에 모두 들어가는 케이스 — 작은 원판 여러 장을 쓰면 안 됨.

    순수 utilization 기반이면 작은 원판에 빽빽이 채우는 쪽이 이기기 쉬움.
    pieces_placed 우선 편향이 제대로 작동하면 큰 원판 1장으로 끝내야 함.
    """
    packer = RegionBasedPacker(
        [(2440, 1220, 1), (600, 400, 5)],  # 큰 1장 + 작은 5장
        kerf=5,
        allow_rotation=True,
    )
    # 전부 한 큰 판에 들어갈 수 있는 조각 세트
    plates = packer.pack([(500, 400, 4), (300, 200, 3)])

    placed = sum(len(p['pieces']) for p in plates)
    assert placed == 7, f"{placed}/7 배치"
    # 핵심 주장: 큰 원판 1장만 사용
    assert len(plates) == 1, f"큰 원판 1장이면 충분한데 {len(plates)}장 사용"
    assert plates[0]['width'] == 2440, "큰 원판을 선택해야 함"
```

- [ ] **Step 2: 실행**

```bash
uv run pytest tests/test_multi_stock_integration.py::test_bias_prefers_one_large_plate_over_many_small -v
```

Expected: PASS. 실패 시 `select_best_stock`의 정렬 키 재검토.

- [ ] **Step 3: Commit**

```bash
git add tests/test_multi_stock_integration.py
git commit -m "test: verify board-count minimization bias prevents unnecessary plates"
```

---

### Task 15: 엣지 케이스

**Files:**
- Modify: `tests/test_multi_stock_integration.py`

- [ ] **Step 1: 엣지 테스트 추가**

Append:

```python
import pytest


def test_empty_stocks_raises():
    """stocks 비면 즉시 에러."""
    with pytest.raises(ValueError, match="최소 1개"):
        RegionBasedPacker([], kerf=5, allow_rotation=True)


def test_invalid_stock_raises():
    """음수/0 stock 거부."""
    with pytest.raises(ValueError, match="양수"):
        RegionBasedPacker([(2440, 1220, 0)], kerf=5, allow_rotation=True)
    with pytest.raises(ValueError, match="양수"):
        RegionBasedPacker([(-100, 1220, 1)], kerf=5, allow_rotation=True)


def test_piece_larger_than_all_stocks():
    """모든 stock보다 큰 조각: 배치 실패 + 조기 종료 (무한루프 아님)."""
    packer = RegionBasedPacker(
        [(1000, 500, 3)], kerf=5, allow_rotation=True,
    )
    plates = packer.pack([(2000, 1000, 1)])
    # 미배치지만 종료됨
    placed = sum(len(p['pieces']) for p in plates)
    assert placed == 0


def test_stock_exhaustion_reports_unplaced():
    """Stock 고갈 시 남은 조각은 배치 안 됨."""
    packer = RegionBasedPacker(
        [(600, 400, 1)],  # 1장만
        kerf=5,
        allow_rotation=True,
    )
    plates = packer.pack([(500, 300, 10)])  # 10개 필요
    placed = sum(len(p['pieces']) for p in plates)
    assert placed < 10, "1장에 다 못 들어감"
    assert len(plates) == 1
```

- [ ] **Step 2: 실행**

```bash
uv run pytest tests/test_multi_stock_integration.py -v
```

Expected: 총 테스트 모두 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_multi_stock_integration.py
git commit -m "test: edge cases for empty/invalid stocks, oversized pieces, exhaustion"
```

---

### Task 16: AGENTS.md 5단계 검증 체크리스트

**Files:**
- (검증만, 코드 변경 없음)

- [ ] **Step 1: 전체 테스트 스위트 실행**

```bash
uv run pytest -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 2: CLI 통합 실행 (회전 허용)**

```bash
printf "2440\n1220\n2\n0\n5\ny\n800\n310\n2\n644\n310\n3\n371\n270\n4\n369\n640\n2\n0\n" | uv run woodcut
```

Expected: `11/11` 배치, output PNG 파일 생성. PNG 열어 시각 확인.

- [ ] **Step 3: CLI 통합 실행 (회전 불허 — 협탁 케이스)**

```bash
printf "2440\n1220\n10\n0\n5\nn\n560\n350\n2\n446\n50\n2\n369\n50\n2\n550\n450\n1\n450\n100\n1\n450\n332\n2\n450\n278\n1\n0\n" | uv run woodcut
```

Expected: 11/11 배치, 모든 조각 정확한 크기, PNG 확인.

- [ ] **Step 4: 혼합 재고 CLI 시연**

```bash
printf "2440\n1220\n1\n1000\n600\n3\n0\n5\ny\n800\n600\n4\n400\n300\n6\n0\n" | uv run woodcut
```

Expected: 두 종류 stock 모두 사용 확인, 배치 시각화.

- [ ] **Step 5: Web 전체 플로우 수동 테스트**

```bash
uv run woodcut web
```

브라우저에서 `http://localhost:8000`:
- 원판 2종 입력 (2440×1220 1장 + 1000×600 3장)
- 조각 추가
- "계산" → 결과 SVG 및 각 plate 타이틀의 치수 표시 확인

- [ ] **Step 6: 최종 Commit (문서 업데이트)**

`PLAN.md`에 멀티 stock 기능 요약 단락 추가 (AGENTS.md 문서화 규칙):

```markdown
## 멀티 사이즈 원판 지원 (2026-04-18)

서로 다른 규격 원판을 각기 정해진 수량만큼 보유한 상태에서 Best-Fit Lookahead + 판 수 최소화 편향으로 재단 계획 생성.

입력: `stocks=[(width, height, count), ...]`
선택 규칙: (pieces_placed, utilization) 사전식 비교
```

```bash
git add PLAN.md
git commit -m "docs: add multi-size stocks feature summary to PLAN.md"
```

- [ ] **Step 7: 검증 완료 선언**

모든 태스크 통과 확인:
- ✅ 회귀 (협탁, 기본 케이스)
- ✅ 신규 혼합 재고
- ✅ 편향 검증 (핵심)
- ✅ 엣지 (빈 stocks, 음수, 초과 조각, 고갈)
- ✅ CLI 회전 허용/불허
- ✅ Web UI 수동 확인
- ✅ 문서 업데이트

---

## 자기 검토 체크리스트

### Spec coverage

| Spec 섹션 | 플랜 태스크 |
|---|---|
| §2.1 입력 모델 | Task 4 (`PackingStrategy` 시그니처), Task 9 (API), Task 8 (CLI), Task 10 (UI) |
| §2.2 알고리즘 | Task 2-3 (선택 로직), Task 5 (루프) |
| §2.3 복잡도 | Task 5에서 구현 + Task 16에서 수동 검증 |
| §3.1 Pydantic | Task 9 |
| §3.2 CLI | Task 8 |
| §3.3 Web UI | Task 10, 11 |
| §4 코드 변경 지점 | 전 태스크에 분산 매핑 |
| §5 Plate dict dimension | Task 5 (packer), Task 7 (visualizer), Task 11 (app.js) |
| §6 검증 계획 | Phase 3 (Task 12-16) |
| §7 트레이드오프 | 플랜 범위 외 (인식만) |

모든 섹션 커버됨.

### Placeholder scan

TODO/TBD/"나중에" 없음. 각 코드 스텝에 실제 코드 포함. 테스트 스텝에 실제 assert 포함.

### Type consistency

- `stocks: list[tuple[int, int, int]]` — Task 4, 5, 9, 11 일관
- `select_best_stock(candidates: list[tuple[int, int, float]]) -> int | None` — Task 3 정의, Task 5 사용 일관
- Plate dict 키 `width`, `height` — Task 5 생성, Task 7 소비, Task 11 소비, Task 12 assert 일관

### 실행 시 주의

- Task 5의 `_pack_single_plate`는 기존 `pack()` 본문을 복제한 형태 — 누락된 import (`FreeSpace`)가 있을 수 있으니 실행 전 확인.
- Task 6은 `region_based_split.py`의 현재 구조에 따라 no-op일 수 있음. Step 1 스모크가 통과하면 Step 2 스킵.
- Task 11의 `createPlateSVG` 함수는 기존 app.js에 이미 존재한다고 가정 — 없으면 별도 구현 필요 (별도 태스크 추가).
