---
name: woodcut-preview
description: woodcut 웹 UI를 Claude Preview(mcp__Claude_Preview__*) 패널로 띄우는 방법. `.claude/launch.json`에 등록된 `woodcut-web` 설정을 `preview_start`로 기동해 `http://localhost:8000`을 프리뷰에 노출한다. index.html만 열면 Pyodide의 `fetch('static/*.py')`가 CORS로 막히므로 반드시 로컬 서버를 경유해야 한다. 웹 UI를 눈으로 확인·스크린샷·eval 해야 할 때 호출.
---

# Woodcut 웹 UI — Claude Preview 기동 가이드

woodcut 웹 앱은 **정적 HTML/JS/Python(Pyodide) 번들을 FastAPI가 서빙**하는 구조다.
`index.html`을 `file://`로 직접 열면 `fetch('static/packing.py')`가 CORS/스킴 제약으로 실패하므로,
반드시 로컬 웹서버를 경유해 프리뷰에 노출해야 한다.

## 원칙

- **서버 기동은 항상 `uv run woodcut web`으로** — uvicorn을 직접 호출하지 말 것.
  이 CLI 엔트리는 [web.py:4](../../src/woodcut/web.py:4)의 `run_server()`가 담당하며,
  호스트/포트가 바뀌면 이 한 곳만 고치면 된다.
- **Claude Preview MCP를 우선 사용** — Chrome MCP는 Pyodide 로드 동안 `still loading` 함정이 많다.
  Preview의 `preview_eval`은 expression 기반이라 async IIFE로 감싸면 `await`가 자동 처리된다.
- **Chrome MCP는 수동 탐색·실사용자 관점 회귀가 필요할 때만** 선택 (→ `woodcut-chrome-e2e` 스킬).

## `.claude/launch.json`

프로젝트 루트에 이미 커밋되어 있다:

```json
{
  "version": "0.0.1",
  "configurations": [
    {
      "name": "woodcut-web",
      "runtimeExecutable": "uv",
      "runtimeArgs": ["run", "woodcut", "web"],
      "port": 8000
    }
  ]
}
```

`port`는 `run_server()`가 바인딩하는 8000과 일치시켜 둔다.

## 표준 플로우

```
# 1. 프리뷰 기동 (이미 돌고 있으면 reused=true로 재활용)
mcp__Claude_Preview__preview_start(name: "woodcut-web")
→ { serverId: "...", port: 8000, reused: false|true }

# 2. 눈으로 확인
mcp__Claude_Preview__preview_screenshot(serverId)

# 3. 상태·계산 검증 (Pyodide 준비까지 자동 대기)
mcp__Claude_Preview__preview_eval(serverId, expression: `
(async () => {
  loadPreset('basic');
  stocks[0].count = 2;
  renderStocks();
  await calculateCutting();
  return {
    status: document.getElementById('status').textContent,
    total: document.getElementById('statTotal').innerText,
    plateCount: document.querySelectorAll('.plate-card').length,
    warning: !!document.querySelector('.warning-banner'),
  };
})()
`)
```

## 준비 상태 판단

Pyodide 초기화는 비동기라 최초 한두 초는 계산이 불가능하다.

- UI 상태: `document.getElementById('status').classList.contains('ready')`
- 내부 플래그: `typeof packerReady !== 'undefined' && packerReady === true`
- `loadPyodide`는 CDN에서 WASM/stdlib를 받아오므로 저속 회선에서는 수 초 걸림 — `preview_eval`의 async IIFE로 `while (!packerReady) await new Promise(r=>setTimeout(r,100))` 로 가드 가능.

## 상태 동기화 — input 이벤트 주의

- `stocks` / `pieces` 는 각 입력 `input` 이벤트 리스너로 동기화된다.
- `preview_eval`로 값을 바꾸려면 **state array를 직접 건드리고 re-render 호출**이 가장 안전하다:
  ```js
  stocks[0].count = 2;
  renderStocks();
  // 또는
  pieces.push({id: Date.now()+Math.random(), width: 500, height: 300, count: 4});
  renderPieces();
  ```
- DOM input value를 직접 세팅하려면 `dispatchEvent(new Event('input', {bubbles:true}))` 필수.

## 캐시 무효화

`app.js`/`style.css`는 브라우저 캐시를 타므로 고치자마자 프리뷰를 새로고침:

```
mcp__Claude_Preview__preview_eval(serverId, expression: "location.reload()")
```

`static/*.py`는 app.js 안에서 `?v=${Date.now()}` 캐시버스터가 붙어 있어 reload만으로 최신본이 적용된다.

## 재기동이 필요한 경우

- `server.py` 또는 `cli.py` 등 **Python 서버 코드** 수정 시 (프로세스 재시작 없이는 미반영).
- 포트가 꼬이거나 좀비 프로세스가 잡혀 있을 때.

```
mcp__Claude_Preview__preview_list()                 # serverId 확인
mcp__Claude_Preview__preview_stop(serverId)
mcp__Claude_Preview__preview_start(name: "woodcut-web")
```

## 정리

```
mcp__Claude_Preview__preview_stop(serverId)
```
세션 종료 시 자동 정리되지만, 장시간 작업 후 명시적 정리가 권장됨.

## 체크리스트

- [ ] `index.html` · `style.css` · `app.js` 를 수정했다 → reload로 충분
- [ ] `server.py` · `web.py` · `cli.py` 를 수정했다 → stop + start 재기동
- [ ] 스크린샷으로 레이아웃·색상·간격 눈으로 확인
- [ ] `preview_eval` 로 `packerReady`, `document.getElementById('status')`, `statTotal` 등 검증
- [ ] 브라우저 상호작용 (드래그·클립보드·실제 마우스 hover 계측) 은 Chrome MCP로 (→ `woodcut-chrome-e2e`)
