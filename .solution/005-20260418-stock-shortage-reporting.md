# 원판 재고 부족 시 명시적 리포트 — 디자인 + 구현 플랜

- **작성일**: 2026-04-18
- **작성자**: Hong Segi (khris@khrislog.net) + Claude
- **상태**: 승인됨 (사용자 승인 2026-04-18)
- **관련 스펙**: `.solution/004-20260418-multi-size-stocks.md` §6.6 "엣지 케이스"

## 1. 배경과 문제

멀티 사이즈 원판 기능([004](004-20260418-multi-size-stocks.md)) 도입 후 발견된 버그:

> **사용자가 제공한 원판 수량이 부족해 일부 조각이 배치되지 못해도, 프로그램이 아무 말 없이 "성공"으로 결과를 보여준다.**

사용자는 이 상태에서 실제 재단에 들어가면 조각이 부족해지는 상황에 처한다.

### 근본 원인

[`region_based.py:127-128`](../src/woodcut/strategies/region_based.py)에서 `print()` 콘솔 경고만 수행하고 `pack()` 반환값(`list[dict]`)에는 미배치 정보가 없다.

- CLI([`interactive.py:125`](../src/woodcut/interactive.py))는 검증 없이 `visualize_solution()`으로 전달
- Web API([`server.py:89-90`](../src/woodcut/web_app/server.py))는 `success=True` 고정
- Pyodide([`app.js:310`](../src/woodcut/web_app/static/app.js))도 `success: True` 고정
- 테스트([`test_multi_stock_integration.py:125`](../tests/test_multi_stock_integration.py))는 "명시 리포트" 여부 미검증

설계서 004 §6.6은 "Stock 고갈: 배치 불가 조각 리스트를 명시 리포트, 예외 아님"을 요구했으나 구현에 반영되지 않았다.

## 2. 설계 결정

### 2.1 `pack()` 반환 형태: `tuple[list[dict], list[dict]]`

```python
def pack(self, pieces) -> tuple[list[dict], list[dict]]:
    ...
    return plates, unplaced
```

- `unplaced`: `remaining_pieces` 내부 dict 그대로 (`expand_pieces()` 결과 구조)
- 단순 추가 값 반환이 아니라 튜플 언팩을 강제해 호출자가 누락할 수 없게 만든다.

### 2.2 성공/실패 구분

- `success = len(unplaced) == 0`
- 예외는 **던지지 않는다** (설계서 §6.6)
- 미배치 조각 목록은 크기별로 집계해 사용자에게 노출

### 2.3 제거: 라이브러리 내부 `print` 경고

`region_based.py`의 `print("⚠️  미배치 조각 ...")`은 제거. 출력 책임은 CLI/웹 UI 레이어로 이관해 로직이 순수해지고 테스트가 깔끔해진다.

## 3. 변경 대상

| 파일 | 변경 |
|---|---|
| `src/woodcut/strategies/region_based.py` | `pack()` 시그니처를 `(plates, unplaced)` 튜플 반환으로 변경, 콘솔 경고 제거 |
| `src/woodcut/strategies/region_based_split.py` | `pack()` 오버라이드 없음 — 자동 반영 |
| `src/woodcut/interactive.py` | 언팩 후 미배치 조각 크기별 집계 경고 출력 |
| `src/woodcut/web_app/server.py` | `CuttingResponse.unplaced_pieces` 필드 추가, `success = len(unplaced) == 0` |
| `src/woodcut/web_app/static/app.js` | Pyodide 응답에 `unplaced_pieces` 포함, `displayResult()`에 경고 배너 |
| `tests/test_multi_stock_integration.py` | 기존 `plates = packer.pack(...)`를 언팩 형태로 수정, `unplaced` 명시 어설트 추가 |
| `PLAN.md` | "원판 부족 시 명시 리포트" 섹션 추가 |

## 4. 재사용

- `region_based.py:111-114`의 `placed_sizes` 집계 패턴을 CLI/UI에서 동일 활용 (`Counter` 또는 dict)
- `expand_pieces()` 결과 dict를 그대로 `unplaced`로 흘려 보내면 되므로 신규 자료형 불필요

## 5. 검증 계획 (AGENTS.md 5단계 체크리스트 적용)

### 5.1 수치 검증 — 단위 테스트

```bash
uv run pytest tests/test_multi_stock_integration.py -v
uv run pytest  # 전체
```

- 신규 어설트: `len(unplaced)`, 크기별 수량 합계
- `placed + len(unplaced) == total_input` 불변식

### 5.2 시각적 검증 — CLI 스모크

Bash 파이프로 자동 실행 후 출력 grep 검증:

```bash
# 재고 부족: 경고 발생해야 함
echo -e "600\n400\n1\n0\n5\ny\n500\n300\n10\n0\n0\n" | uv run woodcut 2>&1 | tee /tmp/woodcut_shortage.log
grep -q "원판 재고 부족" /tmp/woodcut_shortage.log
grep -q "500×300" /tmp/woodcut_shortage.log

# 회귀(협탁): 경고 없어야 함
echo -e "2440\n1220\n10\n0\n5\nn\n560\n350\n2\n446\n50\n2\n369\n50\n2\n550\n450\n1\n450\n100\n1\n450\n332\n2\n450\n278\n1\n0\n0\n" | uv run woodcut 2>&1 | tee /tmp/woodcut_hyuptag.log
! grep -q "원판 재고 부족" /tmp/woodcut_hyuptag.log
```

### 5.3 회귀 테스트

- 협탁 preset(`project_test_case_hyuptag.md` 메모리): 기존과 동일 판 수·배치 유지, `unplaced == []`
- 회전 허용/불허 양쪽

### 5.4 Web UI E2E — Chrome MCP

1. `uv run python -m woodcut web` 백그라운드 실행
2. `mcp__Claude_in_Chrome__navigate` → `http://localhost:8000`
3. `mcp__Claude_in_Chrome__form_input`으로 재고 부족 입력
4. `mcp__Claude_in_Chrome__read_network_requests`로 `/api/cut` 응답 `success=false`, `unplaced_pieces` 확인
5. `mcp__Claude_in_Chrome__read_page`로 경고 배너·미배치 목록 렌더링 확인
6. 성공 시나리오도 한 번 확인 (`success=true`, `unplaced_pieces=[]`)
7. `read_console_messages`로 JS 에러 없음 확인

### 5.5 엣지 케이스

- `test_piece_larger_than_all_stocks`: 모든 stock보다 큰 조각 → `unplaced == 1`
- Stock 0개: 기존 `test_empty_stocks_raises` 유지 (ValueError)

### 5.6 제약 조건

- Guillotine cut / kerf / ±1mm 치수 정확성은 변경 없음 (패킹 로직 자체는 손대지 않음)

## 6. 알려진 한계

- 미배치 조각을 줄이기 위한 알고리즘 재시도(예: 덜 탐욕적인 선택)는 본 작업 스코프 밖. 단순히 "사용자에게 알린다"가 목표.
- `unplaced_pieces`의 dict 구조(expand_pieces 결과 그대로)는 내부 키(`placed_w/h` 등)가 일부 남아 있을 수 있음 — UI에서는 `width`/`height`만 사용.

## 7. 구현 순서

1. `region_based.py` 반환 타입 변경
2. `interactive.py` 경고 로직
3. `server.py` 모델·핸들러
4. `app.js` Pyodide·UI
5. 테스트 수정 및 추가
6. `PLAN.md` 문서화
7. pytest 전체 실행
8. CLI 스모크 실행
9. Chrome MCP E2E 검증
