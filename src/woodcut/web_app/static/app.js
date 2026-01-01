// Pyodide 초기화
let pyodide = null;
let packerReady = false;

// Pyodide 로드 및 초기화
async function initPyodide() {
    showStatus('Python 환경 로딩 중...', 'loading');

    try {
        // Pyodide 로드
        pyodide = await loadPyodide();

        // 1. 기본 클래스 로드 (packing.py)
        const packingResponse = await fetch(`static/packing.py?v=${Date.now()}`);
        const packingCode = await packingResponse.text();
        await pyodide.runPythonAsync(packingCode);

        // 2. RegionBasedPacker 로드 (region_based.py)
        const regionResponse = await fetch(`static/region_based.py?v=${Date.now()}`);
        let regionCode = await regionResponse.text();

        // import 문 제거 (이미 로드됨)
        regionCode = regionCode.replace(/from __future__ import annotations\n/g, '');
        regionCode = regionCode.replace(/from \.\.packing import[^\n]*\n/g, '');

        await pyodide.runPythonAsync(regionCode);

        packerReady = true;
        showStatus('준비 완료', 'success');

    } catch (error) {
        console.error('Pyodide 초기화 실패:', error);
        showStatus(`초기화 실패: ${error.message}`, 'error');
    }
}

// 페이지 로드 시 Pyodide 초기화 및 사용자 프리셋 로드
window.addEventListener('DOMContentLoaded', () => {
    initPyodide();
    loadUserPresets();
});

// 프리셋 데이터
const PRESETS = {
    'basic': [
        [800, 310, 2],
        [644, 310, 3],
        [371, 270, 4],
        [369, 640, 2]
    ],
    'cabinet': [
        [600, 400, 4], // 측판, 천판, 지판
        [560, 380, 2], // 선반
        [595, 395, 2]  // 문짝
    ],
    'shelf': [
        [1800, 300, 2], // 긴 기둥
        [800, 300, 5],  // 선반판
        [1800, 800, 1]  // 뒷판
    ]
};

// 프리셋 로드
function loadPreset(presetId) {
    if (!presetId) return;
    
    let pieces;
    if (PRESETS[presetId]) {
        pieces = PRESETS[presetId];
    } else {
        const userPresets = JSON.parse(localStorage.getItem(USER_PRESETS_KEY) || '{}');
        if (userPresets[presetId]) {
            pieces = userPresets[presetId];
        }
    }

    if (!pieces) return;
    
    const piecesList = document.getElementById('piecesList');
    piecesList.innerHTML = ''; // 기존 목록 초기화
    
    pieces.forEach(p => {
        const newRow = document.createElement('div');
        newRow.className = 'piece-row';
        newRow.innerHTML = `
            <input type="number" class="piece-width" value="${p[0]}" min="1" placeholder="너비">
            <span>×</span>
            <input type="number" class="piece-height" value="${p[1]}" min="1" placeholder="높이">
            <span>×</span>
            <input type="number" class="piece-count" value="${p[2]}" min="1" placeholder="개수">
            <button class="btn-remove" onclick="removePiece(this)">✕</button>
        `;
        piecesList.appendChild(newRow);
    });
    
    showStatus(`프리셋 '${presetId}' 로드 완료`, 'success');
}

const USER_PRESETS_KEY = 'woodcut_user_presets';

// 사용자 프리셋 로드 및 드롭다운 갱신
function loadUserPresets() {
    const userPresets = JSON.parse(localStorage.getItem(USER_PRESETS_KEY) || '{}');
    const group = document.getElementById('userPresetsGroup');
    group.innerHTML = '';
    
    Object.keys(userPresets).forEach(name => {
        const option = document.createElement('option');
        option.value = name;
        option.textContent = name;
        group.appendChild(option);
    });
}

// 현재 설정을 프리셋으로 저장
function saveCurrentAsPreset() {
    const pieces = [];
    const rows = document.querySelectorAll('.piece-row');
    
    rows.forEach(row => {
        const w = parseInt(row.querySelector('.piece-width').value);
        const h = parseInt(row.querySelector('.piece-height').value);
        const c = parseInt(row.querySelector('.piece-count').value);
        
        if (w > 0 && h > 0 && c > 0) {
            pieces.push([w, h, c]);
        }
    });

    if (pieces.length === 0) {
        alert('저장할 조각 정보가 없습니다.');
        return;
    }

    const presetName = prompt('프리셋 이름을 입력하세요:');
    if (!presetName) return;

    const userPresets = JSON.parse(localStorage.getItem(USER_PRESETS_KEY) || '{}');
    userPresets[presetName] = pieces;
    localStorage.setItem(USER_PRESETS_KEY, JSON.stringify(userPresets));

    loadUserPresets();
    document.getElementById('presetSelect').value = presetName;
    showStatus(`프리셋 '${presetName}' 저장 완료`, 'success');
}

// 현재 선택된 사용자 프리셋 삭제
function deleteCurrentPreset() {
    const select = document.getElementById('presetSelect');
    const presetName = select.value;
    
    if (!presetName) return;
    if (PRESETS[presetName]) {
        alert('기본 프리셋은 삭제할 수 없습니다.');
        return;
    }

    if (!confirm(`프리셋 '${presetName}'을(를) 삭제하시겠습니까?`)) {
        return;
    }

    const userPresets = JSON.parse(localStorage.getItem(USER_PRESETS_KEY) || '{}');
    if (userPresets[presetName]) {
        delete userPresets[presetName];
        localStorage.setItem(USER_PRESETS_KEY, JSON.stringify(userPresets));
        loadUserPresets();
        select.value = '';
        showStatus(`프리셋 '${presetName}' 삭제 완료`, 'success');
    }
}

// 조각 추가
function addPiece() {
    const piecesList = document.getElementById('piecesList');
    const newRow = document.createElement('div');
    newRow.className = 'piece-row';
    newRow.innerHTML = `
        <input type="number" class="piece-width" min="1" placeholder="너비">
        <span>×</span>
        <input type="number" class="piece-height" min="1" placeholder="높이">
        <span>×</span>
        <input type="number" class="piece-count" value="1" min="1" placeholder="개수">
        <button class="btn-remove" onclick="removePiece(this)">✕</button>
    `;
    piecesList.appendChild(newRow);
    
    // 포커스 자동 이동
    newRow.querySelector('.piece-width').focus();
}

// 조각 제거
function removePiece(button) {
    button.parentElement.remove();
}

// 상태 메시지 표시
function showStatus(message, type) {
    const status = document.getElementById('status');
    status.textContent = message;
    status.className = `status ${type}`;
}

// 재단 계획 생성
async function calculateCutting() {
    if (!packerReady) {
        showStatus('Python 환경이 아직 준비되지 않았습니다', 'error');
        return;
    }

    showStatus('계산 중...', 'loading');

    // 입력 수집
    const plateWidth = parseInt(document.getElementById('plateWidth').value);
    const plateHeight = parseInt(document.getElementById('plateHeight').value);
    const kerf = parseInt(document.getElementById('kerf').value);
    const allowRotation = document.getElementById('allowRotation').checked;

    const pieces = [];
    const pieceRows = document.querySelectorAll('.piece-row');

    for (const row of pieceRows) {
        const width = parseInt(row.querySelector('.piece-width').value);
        const height = parseInt(row.querySelector('.piece-height').value);
        const count = parseInt(row.querySelector('.piece-count').value);

        if (width && height && count) {
            pieces.push([width, height, count]);
        }
    }

    if (pieces.length === 0) {
        showStatus('조각을 추가해주세요', 'error');
        return;
    }

    try {
        // Python에서 패킹 실행
        pyodide.globals.set('pieces_input', pieces);
        pyodide.globals.set('plate_width', plateWidth);
        pyodide.globals.set('plate_height', plateHeight);
        pyodide.globals.set('kerf', kerf);
        pyodide.globals.set('allow_rotation', allowRotation);

        const result = await pyodide.runPythonAsync(`
packer = RegionBasedPacker(plate_width, plate_height, kerf, allow_rotation)
plates = packer.pack(pieces_input)

# 통계 계산
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

        const data = result.toJs({dict_converter: Object.fromEntries});

        // 결과 표시
        displayResult(data, plateWidth, plateHeight, kerf);
        showStatus('계산 완료!', 'success');

    } catch (error) {
        console.error('Error:', error);
        showStatus(`오류 발생: ${error.message}`, 'error');
    }
}

// 결과 표시
function displayResult(data, plateWidth, plateHeight, kerf) {
    const statsDiv = document.getElementById('resultStats');
    const visualDiv = document.getElementById('visualization');

    // 통계 표시
    const efficiency = (data.placed_pieces / data.total_pieces * 100).toFixed(1);
    statsDiv.innerHTML = `
        <div><strong>총 조각:</strong> ${data.total_pieces}개</div>
        <div><strong>배치 조각:</strong> ${data.placed_pieces}개</div>
        <div><strong>사용 원판:</strong> ${data.plates_used}장</div>
        <div><strong>배치율:</strong> ${efficiency}%</div>
    `;

    // SVG 시각화
    visualDiv.innerHTML = '';

    data.plates.forEach((plate, plateIndex) => {
        const svgContainer = document.createElement('div');
        svgContainer.style.marginBottom = '30px';

        const title = document.createElement('h3');
        title.textContent = `원판 ${plateIndex + 1}`;
        title.style.textAlign = 'center';
        title.style.marginBottom = '10px';
        svgContainer.appendChild(title);

        const svg = createPlateSVG(plate, plateWidth, plateHeight, kerf);
        svgContainer.appendChild(svg);

        visualDiv.appendChild(svgContainer);
    });
}

// SVG 생성
function createPlateSVG(plate, plateWidth, plateHeight, kerf) {
    const scale = 0.3; // 화면에 맞게 축소
    const padding = 40;
    const svgWidth = plateWidth * scale + padding * 2;
    const svgHeight = plateHeight * scale + padding * 2;

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', svgWidth);
    svg.setAttribute('height', svgHeight);
    svg.setAttribute('viewBox', `0 0 ${svgWidth} ${svgHeight}`);

    // 배경 (원판)
    const plateBg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    plateBg.setAttribute('x', padding);
    plateBg.setAttribute('y', padding);
    plateBg.setAttribute('width', plateWidth * scale);
    plateBg.setAttribute('height', plateHeight * scale);
    plateBg.setAttribute('fill', '#f9f9f9');
    plateBg.setAttribute('stroke', '#333');
    plateBg.setAttribute('stroke-width', '2');
    svg.appendChild(plateBg);

    // 조각 색상 팔레트
    const colors = [
        '#3498db', '#e74c3c', '#2ecc71', '#f39c12',
        '#9b59b6', '#1abc9c', '#34495e', '#e67e22',
        '#95a5a6', '#d35400', '#c0392b', '#27ae60'
    ];

    // 조각 그리기
    plate.pieces.forEach((piece, index) => {
        const x = padding + piece.x * scale;

        // Y축 변환: matplotlib(좌하단 원점) → SVG(좌상단 원점)
        const actualW = (piece.rotated ? piece.height : piece.width) * scale;
        const actualH = (piece.rotated ? piece.width : piece.height) * scale;
        const pieceHeight = piece.rotated ? piece.width : piece.height;
        const y = padding + (plateHeight - piece.y - pieceHeight) * scale;

        // 조각 사각형
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x', x);
        rect.setAttribute('y', y);
        rect.setAttribute('width', actualW);
        rect.setAttribute('height', actualH);
        rect.setAttribute('fill', colors[index % colors.length]);
        rect.setAttribute('fill-opacity', '0.7');
        rect.setAttribute('stroke', '#333');
        rect.setAttribute('stroke-width', '1');
        svg.appendChild(rect);

        // 조각 번호 (좌상단)
        const pieceNum = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        pieceNum.setAttribute('x', x + 5);
        pieceNum.setAttribute('y', y + 15);
        pieceNum.setAttribute('font-size', '12');
        pieceNum.setAttribute('font-weight', 'bold');
        pieceNum.setAttribute('fill', 'white');
        pieceNum.textContent = `#${index + 1}`;
        svg.appendChild(pieceNum);

        // 조각 크기 (중앙)
        const sizeText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        sizeText.setAttribute('x', x + actualW / 2);
        sizeText.setAttribute('y', y + actualH / 2);
        sizeText.setAttribute('text-anchor', 'middle');
        sizeText.setAttribute('dominant-baseline', 'middle');
        sizeText.setAttribute('font-size', '11');
        sizeText.setAttribute('fill', 'white');
        sizeText.setAttribute('font-weight', 'bold');
        sizeText.textContent = `${piece.width}×${piece.height}${piece.rotated ? ' ↻' : ''}`;
        svg.appendChild(sizeText);
    });

    // 절단선 그리기
    if (plate.cuts) {
        plate.cuts.forEach((cut, index) => {
            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');

            // direction: 'H' (horizontal) or 'V' (vertical)
            const isHorizontal = cut.direction === 'H';

            if (isHorizontal) {
                // Y축 변환: matplotlib(좌하단) → SVG(좌상단)
                const y = padding + (plateHeight - cut.position) * scale;
                const x1 = padding + (cut.start || 0) * scale;
                const x2 = padding + (cut.end || plateWidth) * scale;
                line.setAttribute('x1', x1);
                line.setAttribute('y1', y);
                line.setAttribute('x2', x2);
                line.setAttribute('y2', y);
            } else {
                const x = padding + cut.position * scale;
                // Y축 변환: start/end도 뒤집기
                const y1 = padding + (plateHeight - (cut.start || 0)) * scale;
                const y2 = padding + (plateHeight - (cut.end || plateHeight)) * scale;
                line.setAttribute('x1', x);
                line.setAttribute('y1', y1);
                line.setAttribute('x2', x);
                line.setAttribute('y2', y2);
            }

            line.setAttribute('stroke', '#e74c3c');
            line.setAttribute('stroke-width', '1.5');
            line.setAttribute('stroke-dasharray', '5,3');
            svg.appendChild(line);

            // 절단선 번호 (선의 중간 지점에 표시)
            const cutLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');

            let labelX, labelY;
            if (isHorizontal) {
                // 가로선: x는 선의 중간, y는 선 위치보다 약간 위
                const x1 = padding + (cut.start || 0) * scale;
                const x2 = padding + (cut.end || plateWidth) * scale;
                labelX = (x1 + x2) / 2;
                // Y축 변환
                labelY = padding + (plateHeight - cut.position) * scale - 3;
            } else {
                // 세로선: x는 선 위치보다 약간 오른쪽, y는 선의 중간
                // Y축 변환
                const y1 = padding + (plateHeight - (cut.start || 0)) * scale;
                const y2 = padding + (plateHeight - (cut.end || plateHeight)) * scale;
                labelX = padding + cut.position * scale + 3;
                labelY = (y1 + y2) / 2;
            }

            cutLabel.setAttribute('x', labelX);
            cutLabel.setAttribute('y', labelY);
            cutLabel.setAttribute('font-size', '10');
            cutLabel.setAttribute('font-weight', 'bold');
            cutLabel.setAttribute('fill', '#e74c3c');
            cutLabel.setAttribute('text-anchor', 'middle');
            cutLabel.setAttribute('dominant-baseline', 'middle');
            cutLabel.setAttribute('stroke', 'white');
            cutLabel.setAttribute('stroke-width', '3');
            cutLabel.setAttribute('paint-order', 'stroke');
            cutLabel.textContent = `${cut.order || index + 1}`;
            svg.appendChild(cutLabel);
        });
    }

    return svg;
}
