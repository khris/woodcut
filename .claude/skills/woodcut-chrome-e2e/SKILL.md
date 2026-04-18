---
name: woodcut-chrome-e2e
description: woodcut 웹 UI를 Chrome MCP(Claude_in_Chrome) 확장으로 엔드투엔드 검증할 때의 작업 가이드. Pyodide 기반 정적 사이트라 read_page/form_input 대신 javascript_tool 중심 전략이 필요함. 웹 UI 변경·프론트엔드 회귀·displayResult 관련 수정·재고 부족 경고 같은 UX 변경을 검증할 때 호출. Chrome MCP가 `still loading`으로 멈추거나 Pyodide 상태 확인이 필요한 경우 필수.
---

# Woodcut Web UI — Chrome MCP E2E 검증 가이드

woodcut 웹 UI는 **FastAPI로 정적 파일만 서빙하고, 실제 패킹 계산은 브라우저 안 Pyodide에서 동작**하는 구조다. 이 비전형적인 아키텍처 때문에 Chrome MCP 표준 플로우가 종종 막힌다. 이 스킬은 그 함정을 우회하는 방법을 기록한다.

## 핵심 이해

1. **Pyodide가 진짜 엔진**: `app.js`가 Pyodide를 로드해 `packer.pack(pieces_input)`을 브라우저 안에서 실행한다. `/api/cut` 엔드포인트는 존재하지만 실제 UI는 이를 호출하지 않는다.
2. **정적 파일 재동기화는 symlink**: `src/woodcut/web_app/static/region_based.py`는 `../../strategies/region_based.py`로 가는 symlink — 소스 수정 즉시 반영된다. 그러나 브라우저 캐시에 캐시버스터(`?v=...`)가 붙어 있어 새로고침만 하면 최신본을 받는다.
3. **Python 3.14 호환성**: 로컬 uv 환경은 3.14지만 Pyodide는 자체 Python(대개 3.12)을 번들. 서버 측 전용 기능은 Pyodide에서 돌지 않을 수 있음 — 프론트에서 돌리는 코드는 구 Python 문법·표준 라이브러리에 맞춰 작성한다.

## 반복 시나리오: 체크리스트

### 사전 준비

```bash
# 1) 서버 기동 (백그라운드)
uv run woodcut web > /tmp/woodcut_server.log 2>&1  # run_in_background: true

# 2) 소켓 준비 대기
until curl -sf http://localhost:8000 > /dev/null 2>&1; do sleep 1; done
```

서버 재시작이 필요할 때:
```bash
kill $(lsof -t -i:8000) 2>/dev/null  # 기존 프로세스 종료 후 재기동
```

### Chrome MCP 초기화

```
mcp__Claude_in_Chrome__tabs_context_mcp(createIfEmpty: true)
→ tabId 확보
mcp__Claude_in_Chrome__navigate(url: "http://localhost:8000", tabId: ...)
```

## 함정과 회피법

### 함정 1: `read_page`가 `still loading`으로 멈춘다

Pyodide가 WASM/패키지를 내려받는 동안 `chrome.scripting.executeScript`의 `document_idle` 조건이 해결되지 않는다. `document.readyState`는 `complete`여도 소용없다.

**회피**: `read_page`/`form_input` 대신 **`javascript_tool`만 사용**한다. DOM 조회·값 세팅·함수 호출을 직접 JS로 수행.

### 함정 2: `window.pyodide`를 보면 항상 `undefined`

[app.js:2](../../src/woodcut/web_app/static/app.js:2)에서 `let pyodide = null`로 선언 — 모듈 스코프 지역 변수라 `window`에 노출되지 않는다.

**회피 — 준비 상태 판단**:
- UI 텍스트: `document.getElementById('status').textContent === '준비 완료'`
- 내부 플래그: `typeof packerReady !== 'undefined' && packerReady === true` (app.js에 선언)
- 함수 존재: `typeof calculateCutting === 'function'`

### 함정 3: 조각 행이 기본으로 없다

- 원판(`stock-row`)은 `addStockRow()`가 초기 1행(2440×1220×1)을 만든다.
- 조각(`piece-row`)은 기본 0행 — `addPiece()`를 호출해야 행이 생긴다.

### 함정 4: 입력값을 넣어도 내부 `stocks` 배열에 반영 안 됨

`stocks`는 input 이벤트 리스너로 동기화된다. `value` 세팅 후 **반드시** `input` 이벤트를 dispatch하라:

```js
el.value = 600;
el.dispatchEvent(new Event('input', {bubbles: true}));
```

조각은 `calculateCutting()` 내부에서 `.piece-row`들을 다시 훑어 읽으므로 이벤트 dispatch 불필요.

### 함정 5: 비동기 결과를 기다려야 함

`calculateCutting()`는 `async`. `javascript_tool`의 expression은 자동으로 Promise를 resolve하므로 **async IIFE로 감싸고 `await` 사용**:

```js
(async () => {
  // 입력 세팅...
  await calculateCutting();
  const stats = document.getElementById('resultStats');
  return JSON.stringify({
    hasWarning: !!stats.querySelector('.warning-banner'),
    text: stats.innerText,
  });
})()
```

## 표준 검증 템플릿 (재고 부족 + 회귀)

```js
// === 시나리오 1: 재고 부족 ===
(async () => {
  const stock = document.querySelector('.stock-row');
  stock.querySelector('.stock-width').value = 600;
  stock.querySelector('.stock-height').value = 400;
  stock.querySelector('.stock-count').value = 1;
  ['stock-width','stock-height','stock-count'].forEach(c =>
    stock.querySelector('.'+c).dispatchEvent(new Event('input', {bubbles:true}))
  );

  addPiece();
  const pr = document.querySelector('.piece-row');
  pr.querySelector('.piece-width').value = 500;
  pr.querySelector('.piece-height').value = 300;
  pr.querySelector('.piece-count').value = 10;

  await calculateCutting();

  const stats = document.getElementById('resultStats');
  return JSON.stringify({
    hasWarning: !!stats.querySelector('.warning-banner'),
    text: stats.innerText,
  });
})()
// 기대: hasWarning=true, "9개 조각 미배치", "500×300mm × 9개"

// === 시나리오 2: 성공 회귀 ===
// 동일 구조, stock=2440×1220×5, piece=800×310×2
// 기대: hasWarning=false, 배치율 100%
```

## 콘솔·네트워크 확인

```
mcp__Claude_in_Chrome__read_console_messages(
  tabId, pattern: "error|warning|Error|Traceback", onlyErrors: true
)
```
Note: tool 처음 호출 시점부터만 캡처되므로 문제가 페이지 로드 직후에 떴다면 새로고침 필요.

## 정리

```bash
kill $(lsof -t -i:8000) 2>/dev/null
# 탭은 자동으로 남겨두고 다음 세션에서 재활용 가능
```

## 체크리스트: 이 스킬을 언제 쓰는가

- [ ] `app.js`의 `displayResult()` 또는 Pyodide 스니펫을 변경했을 때
- [ ] 프론트 UX(경고 배너, 미배치 표시 등) 추가·수정
- [ ] `pack()`의 반환 구조를 바꿔 UI가 새 필드를 읽어야 할 때
- [ ] `index.html`의 입력 폼 구조 변경
- [ ] Chrome MCP가 `still loading`/`document_idle` 에러로 막힐 때
- [ ] "준비 완료"로 보이는데 JS에서 pyodide 검출이 실패하는 경우

## 안티패턴

- ❌ `read_page` 먼저 호출 → 40초 이상 대기 후 timeout
- ❌ `form_input`으로 input 세팅 → 내부 `stocks` 배열 미동기화 가능 (input 이벤트 의존)
- ❌ `/api/cut`을 curl로 쳐서 웹 UI 검증 통과로 판단 → Pyodide 경로는 따로 테스트해야 함
- ❌ `window.pyodide` polling → 영원히 false
- ❌ 서버 재시작 없이 `server.py` 수정 후 확인 → FastAPI는 기본 --reload 꺼져 있음
