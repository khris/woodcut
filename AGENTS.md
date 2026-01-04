# AI Agent Guidelines - Woodcut Project

## 프로젝트 개요

목재 재단 최적화 도구 - Guillotine Cut 제약 하에서 원판에 조각들을 효율적으로 배치하고 절단 순서를 생성하는 프로젝트

**핵심 제약사항:**
- **Guillotine Cut만 가능** (영역 전체를 관통하는 직선 절단)
- 톱날 두께(kerf) 고려 필요
- 회전 허용/불허 선택 가능

---

## 코드 작성 철학

### 1. Python 최신 문법 우선

```python
# ✅ 좋은 예: match-case 사용 (Python 3.10+)
match cut['type']:
    case 'horizontal':
        process_horizontal(cut)
    case 'vertical':
        process_vertical(cut)

# ❌ 나쁜 예: if-elif-else
if cut['type'] == 'horizontal':
    process_horizontal(cut)
elif cut['type'] == 'vertical':
    process_vertical(cut)

# ✅ 타입 힌트 적극 활용
def pack(self, pieces: list[tuple[int, int, int]]) -> list[dict]:
    ...

# ✅ walrus 연산자 활용
if (req_h := piece.get('height')) > max_height:
    ...
```

### 2. 알고리즘 정확성 > 성능

- Guillotine Cut 제약을 **절대 위반하지 않도록** 주의
- 모든 조각이 정확한 크기로 절단되어야 함 (±1mm 오차 허용)
- 성능 최적화는 정확성이 보장된 후에 고려

### 3. 단순함 유지

- 복잡한 추상화보다 명확한 로직 우선
- 함수/메서드는 한 가지 일만 명확하게 수행
- 주석은 "왜(why)"를 설명, "무엇(what)"은 코드로 표현

---

## 핵심 알고리즘 이해

### RegionBasedPacker

**개념:** 다중 그룹 영역 배치 (1:N 매핑)
- 한 영역에 높이/너비가 비슷한 여러 그룹 배치
- 백트래킹으로 최적 조합 탐색
- 다중 판 지원 (while 루프)

**주의사항:**
- 정확히 같은 크기끼리만 그룹화 (유사 크기 병합 미지원)
- 그룹 단위 회전으로 작업 편의성 확보
- 백트래킹으로 최적 조합 탐색

### 2-Phase Cutting

**Phase 1: Trimming Cuts**
- 조각을 정확한 크기로 트리밍
- **서브그룹화**: 같은 y/x 시작점을 높이/너비별로 분류
- 각 서브그룹마다 독립적인 절단선 생성

**Phase 2: Separation Cuts**
- 트림된 조각들을 개별 분리
- 조각 경계 + kerf 위치에 절단선

**중요:**
- 트리밍이 분리보다 우선 (priority 1000+ vs 낮은 값)
- `placed_w/h`로 이미 트림된 조각 추적
- 절단선은 현재 영역 경계 내에서만 생성

---

## 주요 작업별 가이드

### 알고리즘 수정 시

1. **테스트 케이스 먼저 확인**
   ```bash
   # 회전 허용
   echo -e "2440\n1220\n5\ny" | uv run woodcut

   # 회전 불허
   echo -e "2440\n1220\n5\nn" | uv run woodcut
   ```

2. **디버깅 출력 추가**
   - 영역 경계, 조각 위치, 절단선 위치 출력
   - 작업 완료 후 **반드시 제거**

3. **검증 확인**
   - 모든 조각이 정확한 크기인지 확인
   - Guillotine 제약 위반 없는지 확인
   - 시각화로 결과 확인

### 새 기능 추가 시

1. **기존 알고리즘 유지**
   - RegionBasedPacker는 검증된 알고리즘
   - 기존 로직을 깨뜨리지 않도록 주의

2. **옵션으로 제공**
   - 새 기능은 기본적으로 비활성화
   - CLI 파라미터로 활성화 가능하게

3. **문서 업데이트**
   - PLAN.md에 새 기능 설명 추가
   - 사용 예시 포함

### 버그 수정 시

1. **재현 가능한 테스트 케이스 만들기**
   - 특정 조각 배열로 버그 재현
   - 수정 후 동일 케이스로 검증

2. **근본 원인 파악**
   - 증상만 고치지 말고 원인 해결
   - 다른 케이스에서도 발생 가능한지 확인

3. **회귀 테스트**
   - 기존 테스트 케이스 모두 통과하는지 확인
   - 회전 허용/불허 양쪽 모두 테스트

---

## 코드 구조 이해

### 주요 파일

- **`src/woodcut/__init__.py`**: CLI 엔트리 포인트
- **`src/woodcut/strategies/region_based.py`**: 패킹 알고리즘
- **`src/woodcut/packing.py`**: Guillotine Cut 알고리즘
- **`src/woodcut/visualizer.py`**: 시각화

### 데이터 흐름

```
입력 (pieces)
  ↓
그룹화 (exact size)
  ↓
그룹 옵션 평면화
  ↓
백트래킹 영역 할당
  ↓
영역 내 배치
  ↓
Guillotine Cut 생성 (2-Phase)
  ↓
시각화 + 검증
```

### 핵심 데이터 구조

```python
# 조각
piece = {
    'width': 800,           # 원본 너비
    'height': 310,          # 원본 높이
    'x': 0,                 # 배치 x 좌표
    'y': 0,                 # 배치 y 좌표
    'rotated': False,       # 회전 여부
    'placed_w': 800,        # 실제 너비 (회전 후)
    'placed_h': 310         # 실제 높이 (트림 후)
}

# 절단선
cut = {
    'type': 'horizontal',   # 'horizontal' or 'vertical'
    'position': 315,        # 절단 위치 (y or x)
    'priority': 1002,       # 우선순위
    'affects': 2            # 영향받는 조각 수
}

# 영역
region = {
    'x': 0,                 # 영역 시작 x
    'y': 0,                 # 영역 시작 y
    'width': 2440,          # 영역 너비
    'height': 374,          # 영역 높이
    'pieces': [...]         # 포함된 조각들
}
```

---

## 자주 하는 실수

### ❌ Guillotine 제약 위반

```python
# 잘못된 예: 부분 절단
if piece['x'] < cut_x < piece['x'] + piece['width']:
    # 조각 중간을 자르는 절단선 생성 (잘못됨!)
```

**올바른 방법:** 절단선은 영역 전체를 관통해야 함

### ❌ placed_w/h 미업데이트

```python
# 잘못된 예: 트리밍 후 placed_h 업데이트 안 함
for piece in pieces_crossing:
    # 조각이 절단선을 가로지름 → 트림됨
    pass  # placed_h 업데이트 안 함 (버그!)
```

**올바른 방법:** 트리밍 시 반드시 `placed_h` 설정

### ❌ 서브그룹화 누락

```python
# 잘못된 예: 같은 y의 모든 조각을 하나의 높이로 처리
max_height = max(piece['height'] for piece in pieces_at_y)
cut_y = y_start + max_height  # 일부 조각 잘못 자름!
```

**올바른 방법:** 높이별로 서브그룹화 후 독립 절단선 생성

---

## 문서화 규칙

### 코드 주석

```python
# ✅ 좋은 주석: 왜(why) 설명
# 서브그룹화를 통해 같은 위치, 다른 높이 조각들을 독립 처리
height_subgroups = {}

# ❌ 나쁜 주석: 무엇(what) 반복
# height_subgroups 딕셔너리 생성
height_subgroups = {}
```

### Docstring

```python
def pack(self, pieces: list[tuple[int, int, int]]) -> list[dict]:
    """다중 그룹 영역 배치 패킹

    Args:
        pieces: [(width, height, count), ...] 형식의 조각 목록

    Returns:
        판별 배치 결과 리스트
        각 판은 {'pieces': [...], 'cuts': [...]} 구조
    """
```

### PLAN.md 업데이트

- 새 알고리즘/기능 추가 시 반드시 업데이트
- 예시 코드 포함
- 사용 방법, 주의사항 명시

---

## 성능 고려사항

### 현재 성능 특성

- **조각 수 ~10개**: 즉시 실행 (<1초)
- **조각 수 ~50개**: 수 초 소요
- **조각 수 100개+**: 성능 저하 가능

### 최적화 우선순위

1. **정확성 보장** (최우선)
2. **알고리즘 복잡도** (백트래킹 깊이 제한 등)
3. **세부 최적화** (루프, 메모리 등)

**주의:** 조기 최적화 금지 - 성능 문제가 실제로 발생한 경우에만 최적화

---

## 테스트 전략

### 기본 테스트 케이스

```python
pieces = [
    (800, 310, 2),   # 큰 조각
    (644, 310, 3),   # 중간 조각
    (371, 270, 4),   # 작은 조각
    (369, 640, 2),   # 세로로 긴 조각
]
```

**검증 항목:**
- 11/11개 조각 배치
- 모든 조각 정확한 크기
- Guillotine 제약 준수
- 시각화 이미지 확인

### 엣지 케이스

- **회전 불허**: 세로 조각이 다음 판으로
- **같은 크기 많은 조각**: 그룹화 효과 확인
- **다양한 크기**: 그룹화 효과 확인

---

## 버전 관리

### 커밋 메시지

```bash
# 좋은 예
feat: add similar size group merging
fix: correct trimming cut priority calculation
docs: update PLAN.md with Phase 2 algorithm details

# 나쁜 예
update code
fix bug
changes
```

### 브랜치 전략

- `main`: 안정 버전
- `feature/*`: 새 기능 개발
- `fix/*`: 버그 수정

---

## 질문이 있을 때

1. **PLAN.md 먼저 확인** - 대부분의 기술 문서가 있음
2. **코드 읽기** - 명확하게 작성되어 있음
3. **디버깅 출력 추가** - 동작 과정 이해
4. **테스트 케이스 실행** - 실제 동작 확인

---

## 핵심 원칙 요약

1. ✅ **Guillotine 제약 절대 준수**
2. ✅ **모든 조각 정확한 크기로 절단**
3. ✅ **서브그룹화로 다양한 높이 처리**
4. ✅ **placed_w/h로 트림 상태 추적**
5. ✅ **Python 3.10+ 최신 문법 사용**
6. ✅ **테스트로 정확성 검증**
7. ✅ **문서 업데이트 필수**

---

이 프로젝트는 **정확성**이 핵심입니다.
빠르지만 틀린 결과보다, 느리지만 정확한 결과가 훨씬 낫습니다.

---

## IntelliJ MCP 우선 사용 규칙

**IDE가 연결된 경우, 쉘 명령 대신 JetBrains MCP 도구를 사용하라.**

### 필수 대체 규칙

| 작업 | ❌ 금지 | ✅ 사용 |
|------|--------|---------|
| 파일 읽기 | `cat`, `head`, `tail` | `mcp__jetbrains__get_file_text_by_path` |
| 파일 검색 | `find`, `ls -R` | `mcp__jetbrains__find_files_by_name_keyword` |
| 디렉토리 구조 | `tree`, `ls` | `mcp__jetbrains__list_directory_tree` |
| 텍스트 검색 | `grep`, `rg` | `mcp__jetbrains__search_in_files_by_text` |
| 정규식 검색 | `grep -E`, `rg` | `mcp__jetbrains__search_in_files_by_regex` |
| 파일 수정 | `sed`, `awk`, Edit 도구 | `mcp__jetbrains__replace_text_in_file` |
| 파일 생성 | `touch`, Write 도구 | `mcp__jetbrains__create_new_file` |
| 리네임/리팩토링 | 수동 수정 | `mcp__jetbrains__rename_refactoring` |
| 코드 포맷팅 | - | `mcp__jetbrains__reformat_file` |
| 코드 실행 | Bash | `mcp__jetbrains__execute_run_configuration` |
| 오류 분석 | - | `mcp__jetbrains__get_file_problems` |

### Bash 사용 허용 케이스

다음 경우에만 Bash 도구 사용 허용:
- `git` 명령어
- `uv` 패키지 매니저 명령어
- MCP에 해당 run configuration이 없는 경우의 빌드/테스트
- IDE 터미널로 불가능한 시스템 명령

### 리팩토링 시 필수

- **변수/함수/클래스 이름 변경**: 반드시 `rename_refactoring` 사용
  - 모든 참조를 자동으로 업데이트
  - 수동 텍스트 치환 금지

### 코드 수정 후

1. `mcp__jetbrains__get_file_problems`로 오류 확인
2. 필요시 `mcp__jetbrains__reformat_file`로 포맷팅
