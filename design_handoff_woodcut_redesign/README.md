# Handoff: Woodcut Redesign — Technical CAD Direction

## Overview

`khris/woodcut` 리포의 웹 UI (`src/woodcut/web_app/static/`) 를 재디자인한 결과입니다.
목재 재단(Guillotine Cut) 최적화 도구의 기존 "Craft Studio" 따뜻한 우드 테마를
**CAD / 테크니컬 드로잉** 방향으로 완전히 교체합니다.

## About the Design Files

이 폴더의 `Woodcut Redesign.html`은 **디자인 레퍼런스**입니다 — 의도한 룩앤필,
레이아웃, 인터랙션을 보여주는 HTML 프로토타입이지 그대로 프로덕션에 복사해 넣을
코드가 아닙니다.

실제 구현 작업은 **기존 `src/woodcut/web_app/static/` 환경 안에서 이 디자인을
재현**하는 것입니다:
- 현재 프로젝트는 vanilla HTML + CSS + JS + Pyodide 로 돌아갑니다 (React/Vue 없음)
- 기존 JS 로직 (`app.js`) 과 DOM 구조 (`index.html`) 는 최대한 유지
- `style.css` 는 거의 전체 교체
- `index.html` 은 header / 폼 markup 일부 수정이 필요

## Fidelity

**High-fidelity (hifi)** — 픽셀/컬러/타이포/간격/상호작용이 확정된 목업입니다.
이 문서의 토큰 값과 컴포넌트 사양대로 재현해 주세요. 모든 폼 행동은
목업에서 실제로 동작하도록 구현되어 있으니 그대로 참고할 수 있습니다.

---

## Design Tokens

모두 CSS 변수로 선언. 3개 테마가 있었지만 **Precision 테마가 확정**이므로 그 값만
사용합니다. (다른 두 테마의 `:root` 오버라이드는 삭제해도 됩니다.)

### Color (Precision — 최종 확정)

```css
--paper:       #fafafa;   /* 앱 전체 배경 */
--paper-2:     #f0f0f0;   /* 서브 배경 (status 박스 등) */
--ink:         #0a0a0a;   /* 메인 텍스트, 주요 선 */
--ink-soft:    #4a4a4a;   /* 보조 텍스트, 라벨 */
--ink-ghost:   #9a9a9a;   /* 메타 / 단위 / placeholder */
--rule:        #d8d8d8;   /* 주요 구분선 */
--rule-soft:   #ebebeb;   /* 미묘한 내부 구분선 */
--accent:      #00c2a8;   /* 강조 (CTA hover, 절단선, 치수 강조) */
--accent-soft: #6fe0d0;
--bg-elev:     #ffffff;   /* 입력 영역 / 카드 배경 */
--chip:        #ededed;   /* 칩/태그 */
--dim-line:    #111111;   /* 치수선 잉크 */
```

### Typography

```css
--font-sans: 'Pretendard Variable', Pretendard, -apple-system, BlinkMacSystemFont,
             system-ui, sans-serif;
--font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
```

로드 방법:
```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css" />
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet" />
```

**사용 규칙**
- 한글·기본 UI 텍스트 → Pretendard
- 숫자, 단위, 라벨 (W/H, mm, Drawing No., S01, P01, cut 번호 등) → JetBrains Mono
- 바디: 14px / 1.55 / `letter-spacing: -0.005em` / `word-break: keep-all`

### Spacing & Rules

- 주요 프레임 외곽 padding: `32px 40px 60px`
- 섹션 간 간격: `margin-bottom: 26px`
- 필드 padding: `10px 0`, 구분: `1px solid var(--rule-soft)` (첫 행은 무선)
- 주요 영역 경계선: `1.2px solid var(--ink)` (상·하단, 입력/결과 구분)
- 서브 경계선: `1px solid var(--rule)` / `1px solid var(--rule-soft)`
- 전역 border-radius: **0 (모든 요소 각진 형태)** — CAD 도면 느낌

### Motion

- 모든 hover transition: `120ms` linear 또는 default
- CTA hover: `160ms`
- status blink: `1.4s infinite`

---

## Layout Structure

```
.frame  (max-width 1480px, padding 32/40/60)
├─ .titleblock    ← 상단 제목 블록. border-bottom 1.2px solid --ink, 4열 그리드
│   ├─ .cell.title (logo + 목재 재단기 + Woodcut Optimizer)
│   ├─ .cell Drawing No.
│   ├─ .cell Scale · Unit
│   ├─ .cell Project · Revision (span 2)
│   ├─ .cell Sheet
│   └─ .cell Theme switcher  ← (실제 배포시 제거 가능. 디자인 결정됨)
│
├─ .workspace   (grid-template-columns: 440px 1fr, border-top 1.2px)
│   ├─ .input-col   (padding-right 28px, border-right 1.2px solid --ink)
│   │   ├─ § 00  재단 설정 (kerf / rotation toggle / strategy)
│   │   ├─ § 01  프리셋 (select + 저장/삭제)
│   │   ├─ § 02  보유 원판 목록
│   │   ├─ § 03  조각 목록
│   │   ├─ .cta   "재단 계획 생성 →"
│   │   └─ .status
│   │
│   └─ .result-col  (padding-left 28px, 방안지 배경)
│       ├─ .result-head   (제목 + crumbs)
│       ├─ .stats          (4열: 총 조각 / 배치 조각 / 사용 원판 / 배치율)
│       └─ .plates         (반복되는 .plate-card)
│
└─ .footer   border-top 1.5px solid --ink
```

### 방안지 배경 (결과 컬럼 전용)

입력 컬럼은 순수 배경, **결과 컬럼만** 방안지 그리드:

```css
.result-col {
  background-image:
    linear-gradient(to right, color-mix(in srgb, var(--rule) 32%, transparent) 1px, transparent 1px),
    linear-gradient(to bottom, color-mix(in srgb, var(--rule) 32%, transparent) 1px, transparent 1px),
    linear-gradient(to right, color-mix(in srgb, var(--rule) 16%, transparent) 1px, transparent 1px),
    linear-gradient(to bottom, color-mix(in srgb, var(--rule) 16%, transparent) 1px, transparent 1px);
  background-size: 80px 80px, 80px 80px, 16px 16px, 16px 16px;
  background-position: 28px 0, 28px 0, 28px 0, 28px 0;
}
```

---

## Components

### Title block

- 외곽 border 없음. 하단에만 `1.2px solid --ink`
- 4열 grid, `font-family: var(--font-mono)`, 11px
- 각 cell: `.k` (9.5px / 0.12em / uppercase / ghost 컬러) + `.v` (mono 11px / 500)
- `.cell.title`: logo(30×30 박스 + 내부 십자선) + h(Pretendard 20px/700/-0.02em) + sub(10px/0.22em/uppercase)
- 예시 메타: `Drawing No. WC-YYYY-MM-DD`, `Scale · Unit 1:10 · mm`, `Project WOODCUT v2.0 / REV. A`, `Sheet 01 / 01`

### Section header (§ 00~§ 03)

```
§ 00   재단 설정                       PARAMS
─────────────────────────────────────────────
```
- `.num` mono 10px / 0.14em / ghost
- `.name` Pretendard 13px / 700 / -0.01em
- `.tag` (우측) mono 9.5px / 0.12em / uppercase / ghost
- 하단 구분선: `1.2px solid --ink`, 아래로 `padding-bottom: 7px`, `margin-bottom: 4px`

### Field (설정 라벨 + 컨트롤)

- grid `1fr auto`, `padding: 10px 0`
- 연속 필드 사이 `border-top: 1px solid --rule-soft`
- 라벨: 12.5px / --ink-soft + `.idx` (mono 10px / ghost, 예: `00.1`)
- `.unit`: mono 10px / ghost / uppercase / 0.12em (예: `mm`)

### Input / Select

```css
input[type="number"], input[type="text"], select {
  font: 500 13px var(--font-mono);
  border: none;
  border-bottom: 1.5px solid var(--ink);
  padding: 4px 6px;
  width: 88px;
  text-align: right;   /* number */
  background: transparent;
}
input:focus, select:focus {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 6%, transparent);
}
```
- select는 `text-align: left; width: auto; min-width: 180px;`, 커스텀 화살표 SVG 배경
- 테두리 없음, 하단 밑줄만 — CAD 입력 필드 느낌

### Toggle (ON/OFF)

네모난 세그먼티드 토글:
```
[ OFF | ON ]   ← 활성 쪽이 --ink 배경 + --paper 글자
```
- 외곽 1.5px solid --ink, 내부 각 옵션 padding 4×9px, mono 10px / 0.1em / uppercase
- `data-on="true|false"` 로 활성 옵션 결정

### Row list (원판 / 조각)

- 헤더: `# / W / × / H / · / 수량 / ✕` (mono 9.5px / 0.14em / uppercase / ghost)
- 헤더 아래 `border-bottom: 1px solid --rule`
- 각 행: grid `28px 1fr 12px 1fr 12px 1fr 34px`, `padding: 6px 4px`
- 행 사이 `border-top: 1px solid --rule-soft`
- `.idx` mono 10.5px / ghost — 원판은 `S01`, 조각은 `P01`
- 행 hover: 배경 `color-mix(in srgb, var(--accent) 5%, transparent)`
- 삭제 버튼 `.rm`: 28×28, hover시 --accent 테두리 + 글자

### "추가" 버튼 (원판 추가 / 조각 추가)

**점선 박스 버튼 아님.** 상단 경계선만 있는 텍스트 액션:
```css
.btn-add {
  width: 100%;
  padding: 9px 12px;
  border: none;
  border-top: 1px solid var(--rule);
  background: transparent;
  color: var(--ink-soft);
  font: var(--font-mono); font-size: 11px;
  letter-spacing: 0.14em; text-transform: uppercase;
}
.btn-add:hover { color: var(--accent); }
```
`+` 아이콘은 `::before/::after` 로 14×14 박스 안에 십자선으로 그립니다.

### 프리셋 바

- grid `1fr auto auto` (select + 저장 + 삭제)
- `.btn-s`: 1px solid --rule, 7×12 padding, mono 10px / 0.12em / uppercase / ink-soft
- hover: border + text --ink
- `.btn-s.danger:hover`: --accent 로 강조

### CTA "재단 계획 생성 →"

- 가득 찬 검은색 버튼 (width 100%, padding 18×20)
- 배경 --ink, 글자 --paper, Pretendard 15px / 700
- 좌측: "재단 계획 생성 →", 우측: `.kbd` "⌘ ENTER" (mono 10px / 0.14em / opacity 0.6)
- hover: 배경·border 모두 --accent 로 전환
- 오른쪽 화살표는 `::before` (수평선) + `::after` (45° 회전 꺾쇠) 로 제작

### Status 박스

- 아래 영역, padding 9×14, 배경 --paper-2, 1px solid --rule
- `::before` 8×8 원 + blink 애니메이션 (기본 --accent)
- `.status.ready::before { background: #2d9d4a; animation: none; }` — 준비 완료 상태

### Stats (4열)

- 외곽 border 없음. 상·하단에만 `1.2px solid --ink`
- 각 stat 사이 `border-right: 1px solid --rule`
- `.k`: mono 9.5px / 0.14em / uppercase / ghost + 앞에 6×6 --accent 사각형
- `.v`: mono 28px / 700 / -0.02em + `.unit` (13px / ghost / 500)
- 하단에 4px 높이 `.bar` 진행률 바 (--rule-soft 바탕 + --accent fill)

### Plate card (결과 시각화)

```
───────────────────────────────────────
PLATE 01 / 02   원판 1      SIZE 2440×1220 mm  PCS 9  USE 63.7%
                [SVG 도면]
구분선
● 조각   ┉ 절단선   ─ 치수선          단위: mm · 축척 1:10
```

- 외곽 border 없음. `border-top: 1.2px solid --ink` + `padding-top: 14px`
- 헤더: `.pid` (mono 11px / 0.12em / ghost) + `.pname` (Pretendard 14px / 700), 우측 `.meta` (mono 11px / ink-soft, `i` 라벨은 ghost)
- 도면 영역 `.plate-svg-wrap`: padding 24×0×16, 배경 없음 (방안지는 부모에서)
- legend: mono 10.5px, 3가지 스와치 (조각/절단선/치수선) + 축척 라벨

### SVG 도면 내 스타일 (중요)

```css
.sv-plate       { fill: --bg-elev; stroke: --ink; stroke-width: 1.5; }
.sv-piece       { fill: color-mix(in srgb, --accent 10%, --bg-elev); stroke: --ink; stroke-width: 1; }
.sv-piece.alt   { fill: color-mix(in srgb, --accent 4%, --bg-elev); }
.sv-cut         { stroke: --accent; stroke-width: 1.3; stroke-dasharray: 5 3; fill: none; }
.sv-dim         { stroke: --dim-line; stroke-width: 0.8; fill: none; }
.sv-dim-ext     { stroke: --dim-line; stroke-width: 0.6; fill: none; stroke-dasharray: 2 2; }
.sv-label       { font: 500 10px var(--font-mono); fill: --ink; }
.sv-label-dim   { font: 700 10px var(--font-mono); fill: --dim-line; }
.sv-label-num   { font: 700 11px var(--font-mono); fill: --ink; }
.sv-label-cut   { font: 700 10px var(--font-mono); fill: --accent; }
```

SVG 구성요소:
1. **원판 외곽선** — `.sv-plate`
2. **조각 사각형** — `.sv-piece` / `.sv-piece.alt` 번갈아 (짝/홀) + 좌상단 `#1` 라벨 + 중앙 `800×400` 라벨
3. **절단선** — `.sv-cut` + 원형 뱃지 (fill=--bg-elev, stroke=--accent, r=9) + 절단 순서 번호
4. **치수선**
   - 바닥 수평 치수 (원판 너비): extension line 2개 + 화살표 폴리곤 2개 + 가운데 값 라벨 (배경 사각형으로 선 가림)
   - 우측 수직 치수 (원판 높이): 같은 방식, 값 라벨은 rotate(-90)
   - extension line은 `.sv-dim-ext` (stroke-dasharray 2 2)
5. **원점 마커** — 좌하단 `●` + `(0,0)` 라벨
6. **축 눈금** — 500mm 간격으로 아래/왼쪽 축에 tick + 숫자 라벨

구체적 수치·마진은 `Woodcut Redesign.html` 안의 `renderPlate()` 함수를 참고.

---

## Interactions & Behavior

기존 `app.js` 의 행동을 모두 유지합니다. 추가되거나 달라진 점:

### Rotation toggle
- checkbox 는 `display:none`, `.toggle` 래퍼 클릭 시 체크 토글 + `data-on` 갱신
- CSS로 활성 옵션 하이라이트

### Row count 태그
- 원판 수, 조각 타입·총수량을 섹션 헤더 우측 `.tag` 에 실시간 업데이트
  - 원판: `03 ITEMS`
  - 조각: `04 TYPE · 11 PCS`

### Calculate 버튼
- 기존 로직 그대로 (`calculateCutting()` in app.js)
- 계산 중 `.status` 에 "계산 중... REGION-BASED PACKER RUNNING" + blink
- 완료 시 `.status.ready` 로 전환하고 "완료 · 배치율 100% · 2장 사용" 표시

### Hover / focus
- 모든 인터랙티브 요소 120~160ms transition
- 입력 focus: 밑줄 색 + 배경 accent 6%
- 행 hover: 배경 accent 5%

### 반응형
- 1100px 이하: workspace 1열. input-col border-right 제거 + border-bottom 추가.
  result-col의 방안지 배경 위치를 `0 0` 으로 리셋.
- 600px 이하: frame padding 축소, titleblock 1열, stats 2열

---

## State Management

vanilla JS, module 없이 전역 변수:

- `let stocks = []` — `{id, w, h, c}[]`
- `let pieces = []` — `{id, w, h, c}[]`
- `localStorage.woodcut_user_presets` — `{name: [[w,h,c], ...]}`
- `localStorage.woodcut_theme` — 사용 안 함 (Precision 고정 후 제거 가능)

기존 `app.js` 는 DOM 에서 직접 읽어서 `parseInt` 하는 방식이었는데,
레퍼런스 HTML 은 state array 를 두고 re-render 하는 방식입니다.
기존 방식을 유지해도 괜찮고, array 기반으로 리팩토링해도 좋습니다 — 취향껏.

---

## Files in this Handoff

- `Woodcut Redesign.html` — 전체 디자인 레퍼런스 (인라인 CSS + JS + mock data 포함)
- `README.md` — 이 문서

## Source files to edit (in khris/woodcut repo)

- `src/woodcut/web_app/static/index.html` — titleblock 구조 / section 마크업 추가 필요
- `src/woodcut/web_app/static/style.css` — 거의 전체 교체
- `src/woodcut/web_app/static/app.js` — SVG 렌더링 함수 (`createPlateSVG`) 를 레퍼런스의 `renderPlate()` 로 교체 (치수선·축 눈금·원점 마커·extension line 추가)

## Assets

외부 이미지·아이콘 없음. 모든 아이콘 (로고 십자, + 버튼, 화살표, 토글, drop-caret) 은
CSS pseudo-element 또는 인라인 SVG data URI 로 처리.

## Implementation Tips for Claude Code

1. 먼저 `Woodcut Redesign.html` 을 열어 실제 동작 확인
2. `style.css` 는 `:root { --paper... }` 부터 깔고 위→아래로 컴포넌트 단위로 이식
3. `app.js` 의 `displayResult` / `createPlateSVG` 만 교체하면 도면 스타일이 CAD 로 바뀜
4. 기존 Pyodide 연동·프리셋 저장·계산 로직은 절대 건드리지 말 것
5. 테마 전환 기능은 **구현하지 않음** — Precision 만 사용
6. 모든 border-radius 를 0 으로 통일 (기존 `--radius-xs/sm/lg` 변수 삭제)
