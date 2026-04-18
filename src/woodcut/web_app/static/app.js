// ════════════════════════════════════════════════════════════════
// Woodcut — Precision (CAD / Technical Drawing) front-end
// Pyodide·프리셋·계산 로직은 유지. 렌더링만 state 기반으로 전환.
// ════════════════════════════════════════════════════════════════

const USER_PRESETS_KEY = 'woodcut_user_presets';

const PRESETS = {
    basic:   [[800, 310, 2], [644, 310, 3], [371, 270, 4], [369, 640, 2]],
    cabinet: [[600, 400, 4], [560, 380, 2], [595, 395, 2]],
    shelf:   [[1800, 300, 2], [800, 300, 5], [1800, 800, 1]],
};

let pyodide = null;
let packerReady = false;

let stocks = [];
let pieces = [];
let lastResult = null;  // {data, kerf}

// ─────────────────────────────────────────────
// Title block — Drawing No. (오늘 날짜)
// ─────────────────────────────────────────────
(function initTitleblock() {
    const now = new Date();
    const yyyy = now.getFullYear();
    const mm = String(now.getMonth() + 1).padStart(2, '0');
    const dd = String(now.getDate()).padStart(2, '0');
    const el = document.getElementById('drawingNo');
    if (el) el.textContent = `WC-${yyyy}-${mm}-${dd}`;
})();

// ─────────────────────────────────────────────
// Status
// ─────────────────────────────────────────────
function setStatus(message, cls = '') {
    const s = document.getElementById('status');
    s.textContent = message;
    s.className = 'status ' + cls;
}
// 기존 API 호환용 alias
function showStatus(message, type) {
    const map = { loading: '', success: 'ready', error: 'error' };
    setStatus(message, map[type] ?? '');
}

// ─────────────────────────────────────────────
// Rotation toggle (segmented)
// ─────────────────────────────────────────────
(function initRotationToggle() {
    const wrap = document.getElementById('rotationToggle');
    const input = document.getElementById('allowRotation');
    wrap.addEventListener('click', (e) => {
        e.preventDefault();
        input.checked = !input.checked;
        wrap.dataset.on = input.checked ? 'true' : 'false';
    });
})();

// ─────────────────────────────────────────────
// Stocks
// ─────────────────────────────────────────────
function addStockRow(width = 2440, height = 1220, count = 1) {
    stocks.push({ id: Date.now() + Math.random(), width, height, count });
    renderStocks();
}
function removeStockRow(id) {
    stocks = stocks.filter(s => s.id !== id);
    renderStocks();
}
function renderStocks() {
    const list = document.getElementById('stocksList');
    list.innerHTML = '';
    stocks.forEach((s, i) => {
        const row = document.createElement('div');
        row.className = 'row';
        row.innerHTML = `
            <span class="idx mono">S${String(i + 1).padStart(2, '0')}</span>
            <input type="number" value="${s.width}"  min="1" data-k="width"  aria-label="너비" />
            <span class="x">×</span>
            <input type="number" value="${s.height}" min="1" data-k="height" aria-label="높이" />
            <span class="x">·</span>
            <input type="number" value="${s.count}"  min="1" data-k="count"  aria-label="수량" />
            <button class="rm" aria-label="삭제">✕</button>
        `;
        row.querySelectorAll('input').forEach(inp => {
            inp.addEventListener('input', e => {
                s[e.target.dataset.k] = parseInt(e.target.value) || 0;
            });
        });
        row.querySelector('.rm').addEventListener('click', () => removeStockRow(s.id));
        list.appendChild(row);
    });
    const tag = document.getElementById('stockCountTag');
    tag.textContent = `${String(stocks.length).padStart(2, '0')} ITEM${stocks.length === 1 ? '' : 'S'}`;
}

// ─────────────────────────────────────────────
// Pieces
// ─────────────────────────────────────────────
function addPiece(width = '', height = '', count = 1) {
    pieces.push({ id: Date.now() + Math.random(), width, height, count });
    renderPieces();
    // 포커스를 새 행 첫 입력으로
    requestAnimationFrame(() => {
        const list = document.getElementById('piecesList');
        const last = list.lastElementChild;
        last?.querySelector('input[data-k="width"]')?.focus();
    });
}
function removePiece(id) {
    pieces = pieces.filter(p => p.id !== id);
    renderPieces();
}
function renderPieces() {
    const list = document.getElementById('piecesList');
    list.innerHTML = '';
    pieces.forEach((p, i) => {
        const row = document.createElement('div');
        row.className = 'row';
        row.innerHTML = `
            <span class="idx mono">P${String(i + 1).padStart(2, '0')}</span>
            <input type="number" value="${p.width  ?? ''}" min="1" placeholder="W" data-k="width"  />
            <span class="x">×</span>
            <input type="number" value="${p.height ?? ''}" min="1" placeholder="H" data-k="height" />
            <span class="x">·</span>
            <input type="number" value="${p.count  ?? ''}" min="1" data-k="count" />
            <button class="rm" aria-label="삭제">✕</button>
        `;
        row.querySelectorAll('input').forEach(inp => {
            inp.addEventListener('input', e => {
                const val = parseInt(e.target.value);
                p[e.target.dataset.k] = Number.isFinite(val) ? val : '';
                if (e.target.dataset.k === 'count') updatePieceTag();
            });
        });
        row.querySelector('.rm').addEventListener('click', () => removePiece(p.id));
        list.appendChild(row);
    });
    updatePieceTag();
}
function updatePieceTag() {
    const total = pieces.reduce((s, p) => s + (parseInt(p.count) || 0), 0);
    document.getElementById('pieceCountTag').textContent =
        `${String(pieces.length).padStart(2, '0')} TYPE · ${String(total).padStart(2, '0')} PCS`;
}

// ─────────────────────────────────────────────
// Presets (기존 로직 유지 · state 반영)
// ─────────────────────────────────────────────
function loadPreset(presetId) {
    if (!presetId) return;

    let data = PRESETS[presetId];
    if (!data) {
        const user = JSON.parse(localStorage.getItem(USER_PRESETS_KEY) || '{}');
        data = user[presetId];
    }
    if (!data) return;

    pieces = data.map(([w, h, c]) => ({
        id: Date.now() + Math.random(),
        width: w, height: h, count: c,
    }));
    renderPieces();
    showStatus(`프리셋 '${presetId}' 로드 완료`, 'success');
}

function loadUserPresets() {
    const user = JSON.parse(localStorage.getItem(USER_PRESETS_KEY) || '{}');
    const group = document.getElementById('userPresetsGroup');
    group.innerHTML = '';
    Object.keys(user).forEach(name => {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        group.appendChild(opt);
    });
}

function saveCurrentAsPreset() {
    const data = pieces
        .filter(p => p.width > 0 && p.height > 0 && p.count > 0)
        .map(p => [p.width, p.height, p.count]);

    if (data.length === 0) {
        alert('저장할 조각 정보가 없습니다.');
        return;
    }

    const name = prompt('프리셋 이름을 입력하세요:');
    if (!name) return;

    const user = JSON.parse(localStorage.getItem(USER_PRESETS_KEY) || '{}');
    user[name] = data;
    localStorage.setItem(USER_PRESETS_KEY, JSON.stringify(user));

    loadUserPresets();
    document.getElementById('presetSelect').value = name;
    showStatus(`프리셋 '${name}' 저장 완료`, 'success');
}

function deleteCurrentPreset() {
    const select = document.getElementById('presetSelect');
    const name = select.value;
    if (!name) return;
    if (PRESETS[name]) {
        alert('기본 프리셋은 삭제할 수 없습니다.');
        return;
    }
    if (!confirm(`프리셋 '${name}'을(를) 삭제하시겠습니까?`)) return;

    const user = JSON.parse(localStorage.getItem(USER_PRESETS_KEY) || '{}');
    if (user[name]) {
        delete user[name];
        localStorage.setItem(USER_PRESETS_KEY, JSON.stringify(user));
        loadUserPresets();
        select.value = '';
        showStatus(`프리셋 '${name}' 삭제 완료`, 'success');
    }
}

// ─────────────────────────────────────────────
// Pyodide init (기존 로직 유지)
// ─────────────────────────────────────────────
async function initPyodide() {
    setStatus('Python 환경 로딩 중...');

    try {
        pyodide = await loadPyodide();

        const packingResponse = await fetch(`static/packing.py?v=${Date.now()}`);
        const packingCode = await packingResponse.text();
        await pyodide.runPythonAsync(packingCode);

        const regionResponse = await fetch(`static/region_based.py?v=${Date.now()}`);
        let regionCode = await regionResponse.text();
        regionCode = regionCode.replace(/from __future__ import annotations\n/g, '');
        regionCode = regionCode.replace(/from \.\.packing import[^\n]*\n/g, '');
        await pyodide.runPythonAsync(regionCode);

        const splitResponse = await fetch(`static/region_based_split.py?v=${Date.now()}`);
        let splitCode = await splitResponse.text();
        splitCode = splitCode.replace(/from __future__ import annotations\n/g, '');
        splitCode = splitCode.replace(/from \.region_based import[^\n]*\n/g, '');
        await pyodide.runPythonAsync(splitCode);

        packerReady = true;
        setStatus('READY · 입력 후 계산을 실행하세요', 'ready');
    } catch (error) {
        console.error('Pyodide 초기화 실패:', error);
        setStatus(`초기화 실패: ${error.message}`, 'error');
    }
}

// ─────────────────────────────────────────────
// Calculate (기존 Python 호출 유지)
// ─────────────────────────────────────────────
async function calculateCutting() {
    if (!packerReady) {
        setStatus('Python 환경이 아직 준비되지 않았습니다', 'error');
        return;
    }

    setStatus('계산 중 · REGION-BASED PACKER RUNNING');

    const kerf = parseInt(document.getElementById('kerf').value);
    const allowRotation = document.getElementById('allowRotation').checked;
    const strategy = document.getElementById('strategySelect').value;

    const piecesInput = pieces
        .filter(p => p.width > 0 && p.height > 0 && p.count > 0)
        .map(p => [p.width, p.height, p.count]);

    if (piecesInput.length === 0) {
        setStatus('조각을 추가해주세요', 'error');
        return;
    }
    if (stocks.length === 0) {
        setStatus('원판을 최소 1개 추가해주세요', 'error');
        return;
    }
    const invalidStock = stocks.find(s => s.width <= 0 || s.height <= 0 || s.count <= 0);
    if (invalidStock) {
        setStatus('원판 치수와 수량은 모두 양수여야 합니다', 'error');
        return;
    }

    try {
        pyodide.globals.set('pieces_input', piecesInput);
        pyodide.globals.set('stocks_input', stocks.map(s => [s.width, s.height, s.count]));
        pyodide.globals.set('kerf', kerf);
        pyodide.globals.set('allow_rotation', allowRotation);

        const packerClass = strategy === 'region_based_split'
            ? 'RegionBasedPackerWithSplit'
            : 'RegionBasedPacker';

        const result = await pyodide.runPythonAsync(`
packer = ${packerClass}(stocks_input, kerf, allow_rotation)
plates, unplaced = packer.pack(pieces_input)

total_pieces = sum(p[2] for p in pieces_input)
placed_pieces = total_pieces - len(unplaced)

{
    'success': len(unplaced) == 0,
    'total_pieces': total_pieces,
    'placed_pieces': placed_pieces,
    'plates_used': len(plates),
    'plates': plates,
    'unplaced_pieces': unplaced,
}
        `);

        const data = result.toJs({ dict_converter: Object.fromEntries });
        lastResult = { data, kerf, strategy, allowRotation };
        displayResult(data, kerf, strategy);

        const eff = data.total_pieces === 0 ? 0 : (data.placed_pieces / data.total_pieces * 100).toFixed(0);
        setStatus(`완료 · 배치율 ${eff}% · ${data.plates_used}장 사용`, 'ready');
    } catch (error) {
        console.error('Error:', error);
        setStatus(`오류 발생: ${error.message}`, 'error');
    }
}

// ─────────────────────────────────────────────
// Result rendering
// ─────────────────────────────────────────────
function displayResult(data, kerf, strategy) {
    // crumb
    const crumb = document.getElementById('resultCrumb');
    const stratLabel = strategy === 'region_based_split' ? 'REGION-BASED + SPLIT' : 'REGION-BASED';
    crumb.textContent = `${stratLabel} · KERF ${kerf}mm`;

    // sheet
    const sheet = document.getElementById('sheetNo');
    const total = data.plates_used || 0;
    sheet.textContent = `${String(Math.max(total, 1)).padStart(2, '0')} / ${String(Math.max(total, 1)).padStart(2, '0')}`;

    // stats
    const efficiency = data.total_pieces === 0
        ? 0
        : (data.placed_pieces / data.total_pieces * 100);
    const effText = efficiency.toFixed(1);

    setStat('statTotal', data.total_pieces, 'pcs');
    setStat('statPlaced', data.placed_pieces, 'pcs');
    setStat('statPlates', data.plates_used, 'sheet');
    setStat('statEff', effText, '%');

    setBar('totalBar', 100);
    setBar('placedBar', data.total_pieces === 0 ? 0 : (data.placed_pieces / data.total_pieces * 100));
    setBar('platesBar', Math.min(100, data.plates_used * 25));
    setBar('effBar', efficiency);

    // warning banner (unplaced)
    const warnWrap = document.getElementById('warningBanner');
    const unplaced = data.unplaced_pieces || [];
    if (unplaced.length > 0) {
        const counts = {};
        unplaced.forEach(p => {
            const key = `${p.width}×${p.height}mm`;
            counts[key] = (counts[key] || 0) + 1;
        });
        const items = Object.entries(counts)
            .map(([size, n]) => `<li>${size} × ${n}개</li>`)
            .join('');
        warnWrap.innerHTML = `
            <div class="warning-banner">
                <div class="wb-title">원판 재고 부족 · ${unplaced.length}개 조각 미배치</div>
                <ul>${items}</ul>
                <div class="wb-hint">원판 수량을 늘리거나 조각 크기를 확인하세요.</div>
            </div>
        `;
    } else {
        warnWrap.innerHTML = '';
    }

    // plates
    const container = document.getElementById('platesContainer');
    container.innerHTML = '';
    if (!data.plates || data.plates.length === 0) {
        container.innerHTML = `<div class="empty-plates mono">배치된 원판이 없습니다</div>`;
        return;
    }
    data.plates.forEach((plate, i) => {
        container.appendChild(renderPlate(plate, i + 1, data.plates.length));
    });
}

function setStat(id, value, unit) {
    const el = document.getElementById(id);
    el.innerHTML = `${value}<span class="unit">${unit}</span>`;
}
function setBar(id, pct) {
    const el = document.getElementById(id);
    if (el) el.style.width = `${Math.max(0, Math.min(100, pct))}%`;
}

// ─────────────────────────────────────────────
// SVG plate drawing (CAD technical style)
// ─────────────────────────────────────────────
function renderPlate(plate, num, total) {
    const card = document.createElement('div');
    card.className = 'plate-card';

    const totalArea = plate.width * plate.height;
    const used = plate.pieces.reduce((s, p) => {
        const pw = p.rotated ? p.height : p.width;
        const ph = p.rotated ? p.width : p.height;
        return s + pw * ph;
    }, 0);
    const eff = ((used / totalArea) * 100).toFixed(1);

    card.innerHTML = `
        <header>
            <div class="lbl">
                <span class="pid">PLATE ${String(num).padStart(2, '0')} / ${String(total).padStart(2, '0')}</span>
                <span class="pname">원판 ${num}</span>
            </div>
            <div class="meta">
                <span><i>SIZE</i>${plate.width} × ${plate.height} mm</span>
                <span><i>PCS</i>${plate.pieces.length}</span>
                <span><i>USE</i>${eff}%</span>
            </div>
        </header>
        <div class="plate-svg-wrap"></div>
        <div class="legend">
            <span class="k"><span class="sw"></span>조각 (piece)</span>
            <span class="k"><span class="sw cut"></span>절단선 (cut)</span>
            <span class="k"><span class="sw dim"></span>치수선 (dimension)</span>
            <span class="k" style="margin-left:auto;">단위: mm · 축척 1:10</span>
        </div>
    `;

    const viewW = 920;
    const marginL = 70, marginR = 70, marginT = 70, marginB = 70;
    const scale = (viewW - marginL - marginR) / plate.width;
    const drawH = plate.height * scale;
    const viewH = drawH + marginT + marginB;

    const svg = svgEl('svg', {
        viewBox: `0 0 ${viewW} ${viewH}`,
        width: '100%',
    });

    const X = (x) => marginL + x * scale;
    const Y = (y, h = 0) => marginT + (plate.height - y - h) * scale;
    const W = (w) => w * scale;
    const H = (h) => h * scale;

    // 1. plate outline
    svg.appendChild(svgEl('rect', {
        x: marginL, y: marginT,
        width: W(plate.width), height: H(plate.height),
        class: 'sv-plate',
    }));

    // 2. pieces
    plate.pieces.forEach((p, idx) => {
        const pw = p.rotated ? p.height : p.width;
        const ph = p.rotated ? p.width : p.height;
        const px = X(p.x);
        const py = Y(p.y, ph);

        svg.appendChild(svgEl('rect', {
            x: px, y: py,
            width: W(pw), height: H(ph),
            class: 'sv-piece' + (idx % 2 ? ' alt' : ''),
        }));

        svg.appendChild(svgText({
            x: px + 6, y: py + 14,
            class: 'sv-label-num',
        }, `#${idx + 1}`));

        if (W(pw) > 70 && H(ph) > 30) {
            svg.appendChild(svgText({
                x: px + W(pw) / 2,
                y: py + H(ph) / 2 + 4,
                'text-anchor': 'middle',
                class: 'sv-label',
            }, `${p.width}×${p.height}${p.rotated ? ' ↻' : ''}`));
        }
    });

    // 3. cuts
    (plate.cuts || []).forEach((cut, idx) => {
        let x1, y1, x2, y2, lx, ly;
        if (cut.direction === 'H') {
            const yy = Y(cut.position);
            x1 = X(cut.start || 0);
            x2 = X(cut.end ?? plate.width);
            y1 = y2 = yy;
            lx = (x1 + x2) / 2;
            ly = yy - 6;
        } else {
            const xx = X(cut.position);
            const sy = Y(cut.start || 0);
            const ey = Y(cut.end ?? plate.height);
            x1 = x2 = xx; y1 = sy; y2 = ey;
            lx = xx + 7;
            ly = (y1 + y2) / 2 + 4;
        }

        svg.appendChild(svgEl('line', { x1, y1, x2, y2, class: 'sv-cut' }));

        const badge = svgEl('g', {});
        badge.appendChild(svgEl('circle', {
            cx: lx, cy: ly - 3, r: 9,
            fill: 'var(--bg-elev)',
            stroke: 'var(--accent)',
            'stroke-width': 1,
        }));
        badge.appendChild(svgText({
            x: lx, y: ly,
            'text-anchor': 'middle',
            class: 'sv-label-cut',
        }, String(cut.order || idx + 1)));
        svg.appendChild(badge);
    });

    // 4. overall dimensions — bottom width
    const dimY = marginT + H(plate.height) + 34;
    drawDim(svg, marginL, dimY, marginL + W(plate.width), dimY, `${plate.width}`, 'h');
    svg.appendChild(svgEl('line', {
        x1: marginL, y1: marginT + H(plate.height),
        x2: marginL, y2: dimY + 4,
        class: 'sv-dim-ext',
    }));
    svg.appendChild(svgEl('line', {
        x1: marginL + W(plate.width), y1: marginT + H(plate.height),
        x2: marginL + W(plate.width), y2: dimY + 4,
        class: 'sv-dim-ext',
    }));

    // right height dimension
    const dimX = marginL + W(plate.width) + 36;
    drawDim(svg, dimX, marginT, dimX, marginT + H(plate.height), `${plate.height}`, 'v');
    svg.appendChild(svgEl('line', {
        x1: marginL + W(plate.width), y1: marginT,
        x2: dimX + 4, y2: marginT,
        class: 'sv-dim-ext',
    }));
    svg.appendChild(svgEl('line', {
        x1: marginL + W(plate.width), y1: marginT + H(plate.height),
        x2: dimX + 4, y2: marginT + H(plate.height),
        class: 'sv-dim-ext',
    }));

    // 5. origin marker
    svg.appendChild(svgEl('circle', {
        cx: marginL, cy: marginT + H(plate.height),
        r: 3, fill: 'var(--ink)',
    }));
    svg.appendChild(svgText({
        x: marginL - 8, y: marginT + H(plate.height) + 16,
        'text-anchor': 'end',
        class: 'sv-label-dim',
    }, '(0,0)'));

    // 6. axis ticks (500mm grid)
    for (let v = 500; v < plate.width; v += 500) {
        const px = X(v);
        svg.appendChild(svgEl('line', {
            x1: px, y1: marginT + H(plate.height),
            x2: px, y2: marginT + H(plate.height) + 5,
            class: 'sv-dim',
        }));
        svg.appendChild(svgText({
            x: px, y: marginT + H(plate.height) + 16,
            'text-anchor': 'middle',
            class: 'sv-label-dim',
        }, String(v)));
    }
    for (let v = 500; v < plate.height; v += 500) {
        const py = Y(v);
        svg.appendChild(svgEl('line', {
            x1: marginL - 5, y1: py,
            x2: marginL, y2: py,
            class: 'sv-dim',
        }));
        svg.appendChild(svgText({
            x: marginL - 8, y: py + 3,
            'text-anchor': 'end',
            class: 'sv-label-dim',
        }, String(v)));
    }

    card.querySelector('.plate-svg-wrap').appendChild(svg);
    return card;
}

function drawDim(svg, x1, y1, x2, y2, label, dir) {
    svg.appendChild(svgEl('line', { x1, y1, x2, y2, class: 'sv-dim' }));

    if (dir === 'h') {
        svg.appendChild(svgEl('polygon', {
            points: `${x1},${y1} ${x1 + 6},${y1 - 3} ${x1 + 6},${y1 + 3}`,
            fill: 'var(--dim-line)',
        }));
        svg.appendChild(svgEl('polygon', {
            points: `${x2},${y2} ${x2 - 6},${y2 - 3} ${x2 - 6},${y2 + 3}`,
            fill: 'var(--dim-line)',
        }));
        const cx = (x1 + x2) / 2, cy = y1;
        const g = svgEl('g', {});
        g.appendChild(svgEl('rect', {
            x: cx - 28, y: cy - 8, width: 56, height: 16,
            fill: 'var(--bg-elev)',
        }));
        g.appendChild(svgText({
            x: cx, y: cy + 4,
            'text-anchor': 'middle',
            class: 'sv-label-dim',
        }, label));
        svg.appendChild(g);
    } else {
        svg.appendChild(svgEl('polygon', {
            points: `${x1},${y1} ${x1 - 3},${y1 + 6} ${x1 + 3},${y1 + 6}`,
            fill: 'var(--dim-line)',
        }));
        svg.appendChild(svgEl('polygon', {
            points: `${x2},${y2} ${x2 - 3},${y2 - 6} ${x2 + 3},${y2 - 6}`,
            fill: 'var(--dim-line)',
        }));
        const cx = x1, cy = (y1 + y2) / 2;
        const g = svgEl('g', { transform: `rotate(-90 ${cx} ${cy})` });
        g.appendChild(svgEl('rect', {
            x: cx - 28, y: cy - 8, width: 56, height: 16,
            fill: 'var(--bg-elev)',
        }));
        g.appendChild(svgText({
            x: cx, y: cy + 4,
            'text-anchor': 'middle',
            class: 'sv-label-dim',
        }, label));
        svg.appendChild(g);
    }
}

function svgEl(name, attrs) {
    const e = document.createElementNS('http://www.w3.org/2000/svg', name);
    Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
    return e;
}
function svgText(attrs, text) {
    const e = svgEl('text', attrs);
    e.textContent = text;
    return e;
}

// ─────────────────────────────────────────────
// Wiring
// ─────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
    document.getElementById('addStockBtn').addEventListener('click', () => addStockRow());
    document.getElementById('addPieceBtn').addEventListener('click', () => addPiece());
    document.getElementById('calculateBtn').addEventListener('click', () => calculateCutting());
    document.getElementById('presetSelect').addEventListener('change', (e) => loadPreset(e.target.value));
    document.getElementById('savePresetBtn').addEventListener('click', saveCurrentAsPreset);
    document.getElementById('deletePresetBtn').addEventListener('click', deleteCurrentPreset);

    // ⌘/Ctrl + Enter 단축키
    document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
            e.preventDefault();
            calculateCutting();
        }
    });

    addStockRow();      // 기본 원판 1행 (2440×1220 1장)
    loadUserPresets();
    initPyodide();
});
