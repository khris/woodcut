# 구현 검증 체크리스트

> 작성일: 2026-01-10
> 목적: 구현 완료 후 조기 성공 선언 방지, 체계적 검증 프로세스 확립
> 배경: Multi-Tier Placement 구현 중 3번의 버그가 모두 사용자 지적 후 발견됨

---

## Quick Reference - 구현 완료 후 필수 5단계

**이 5단계를 모두 통과한 후에만 "성공" 선언 가능:**

1. ✓ **수치 검증** (입력 조각 수 == 출력 조각 수)
2. ✓ **PNG 이미지 확인** (육안 검증 필수 - 파일 생성만으로는 부족)
3. ✓ **회귀 테스트** (기존 기능 유지 확인)
4. ✓ **Guillotine 제약 확인** (모든 절단선이 영역 관통)
5. ✓ **엣지 케이스 테스트** (경계 조건 처리 확인)

> **"구현 완료 ≠ 성공"**
> **"검증 완료 = 성공"**

---

## 목차

1. [개요](#1-개요)
2. [구현 전 체크리스트](#2-구현-전-체크리스트)
3. [구현 중 체크리스트](#3-구현-중-체크리스트)
4. [구현 후 필수 검증](#4-구현-후-필수-검증) ★★★
5. [버그 사례 분석](#5-버그-사례-분석)
6. [성공 선언 기준](#6-성공-선언-기준)
7. [체크리스트 템플릿](#7-체크리스트-템플릿)
8. [자주 하는 실수](#8-자주-하는-실수)

---

## 1. 개요

### 1.1 문서의 목적

이 문서는 다음을 위한 체계적인 검증 프로세스를 제공합니다:

- **조기 성공 선언 방지**: 구현 완료 후 충분한 검증 없이 "성공"이라고 판단하는 것을 방지
- **자체 버그 발견**: 사용자 지적 전에 스스로 버그를 발견할 수 있는 체계 제공
- **반복 가능한 프로세스**: 모든 구현 작업에 적용 가능한 일관된 검증 절차

### 1.2 검증의 중요성

> "빠르지만 틀린 결과보다, 느리지만 정확한 결과가 훨씬 낫습니다." - AGENTS.md

Woodcut 프로젝트의 핵심은 **정확성**입니다. Guillotine Cut 제약을 위반하거나 조각 크기가 부정확하면 실제 목재 재단 시 심각한 문제가 발생합니다.

### 1.3 이 문서가 필요한 이유

**Multi-Tier Placement 구현 사례:**
- 3번의 버그 발견 모두 사용자 지적 후
- 매번 "성공" 선언 후 버그 발견
- 체계적 검증 부재로 인한 반복적 패턴

이 문서는 이러한 패턴을 방지하기 위해 작성되었습니다.

---

## 2. 구현 전 체크리스트

### 2.1 요구사항 명확화

- [ ] **사용자 요구사항 문서화**
  - 무엇을 구현해야 하는가?
  - 왜 필요한가?

- [ ] **예상 입력/출력 정의**
  - 입력 형식과 범위
  - 예상 출력 형식
  - 예시 데이터

- [ ] **성공 기준 수치화**
  - 예: "8개 입력 = 8개 출력"
  - 예: "회전 OFF 시 회전된 조각 0개"
  - 측정 가능한 기준 설정

- [ ] **실패 조건 정의**
  - 어떤 경우 실패인가?
  - 예외 상황은 무엇인가?

### 2.2 기존 코드 분석

- [ ] **수정할 파일 목록 작성**
  - 파일 경로와 이유 명시

- [ ] **영향받는 함수/메서드 파악**
  - 호출 관계 추적
  - 데이터 흐름 이해

- [ ] **기존 검증 로직 확인**
  - `packing.py`의 FSM 검증
  - `visualizer.py`의 검증
  - 활용 가능한 기존 메커니즘

- [ ] **데이터 흐름 추적**
  - 입력 → 변환 → 출력 경로 이해

### 2.3 테스트 케이스 설계

- [ ] **기본 케이스 정의**
  - 정상 동작 시나리오
  - 대표적인 입력 데이터

- [ ] **엣지 케이스 정의**
  - 경계 조건 (빈 입력, 1개 조각, 매우 많은 조각)
  - 극단적 크기 (매우 큰 조각, 매우 작은 조각)
  - 특수 조건 (모두 같은 크기, 원판보다 큰 조각)

- [ ] **회귀 테스트 케이스 정의**
  - 기존 기능이 깨지지 않았는지 확인할 케이스
  - 새 기능 OFF 시 동작 확인 케이스

- [ ] **예상 결과 문서화**
  - 각 테스트 케이스의 예상 출력
  - 수치화된 기준 (조각 수, 원판 수, 사용률 등)

### 2.4 검증 기준 사전 정의

- [ ] **수치 검증 항목 나열**
  - 조각 수, 크기, 위치, 사용률 등

- [ ] **시각적 검증 항목 나열**
  - PNG 이미지에서 확인할 사항
  - 절단선 위치, 조각 배치, kerf 간격 등

- [ ] **성능 기준 정의** (있다면)
  - 실행 시간, 메모리 사용량 등

- [ ] **허용 오차 정의**
  - 조각 크기: ±1mm
  - 위치: ±0.1mm 등

---

## 3. 구현 중 체크리스트

### 3.1 단계별 검증

- [ ] **각 함수/메서드 작성 후 단위 테스트**
  - 독립적으로 테스트 가능한지 확인
  - 간단한 입력으로 동작 확인

- [ ] **로깅 출력으로 중간값 확인**
  - 주요 변수값 출력
  - 예상과 실제값 비교

- [ ] **데이터 구조 변경 시 영향 범위 확인**
  - 모든 접근 경로 수정 완료했는지
  - 타입 일관성 유지되는지

### 3.2 로깅 전략

- [ ] **주요 변수값 출력**
  ```python
  print(f"입력 조각 수: {len(pieces)}")
  print(f"그룹 수: {len(groups)}")
  ```

- [ ] **조건 분기 진입 확인**
  ```python
  if enable_multi_tier:
      print("다단 배치 활성화")
  ```

- [ ] **루프 반복 횟수 확인**
  ```python
  for i, plate in enumerate(plates):
      print(f"원판 {i+1}: {len(plate['pieces'])}개 조각")
  ```

- [ ] **⚠️ 경고: 구현 완료 후 디버깅 로그 제거**
  - 커밋 전 모든 디버깅 print 문 삭제
  - 필요한 로그만 남김

### 3.3 중간 검증 포인트

- [ ] **데이터 변환 후 검증**
  - 변환 전후 개수 일치 확인
  - 데이터 무결성 확인

- [ ] **루프 완료 후 검증**
  - 모든 항목이 처리되었는지
  - 누락이나 중복이 없는지

- [ ] **재귀 호출 전후 검증**
  - 입력 조건 만족 확인
  - 반환값 유효성 확인

---

## 4. 구현 후 필수 검증

> **이 섹션이 가장 중요합니다!**
> 모든 항목을 통과한 후에만 "성공" 선언 가능

### 4.1 수치 검증 (Numerical Verification)

#### a) 조각 수 검증

**필수 확인:**
- [ ] **입력 조각 총 개수 계산**
  ```python
  total_input = sum(count for w, h, count in pieces)
  print(f"입력 조각 총 개수: {total_input}")
  ```

- [ ] **출력 조각 총 개수 계산**
  ```python
  total_output = sum(len(plate['pieces']) for plate in plates)
  print(f"출력 조각 총 개수: {total_output}")
  ```

- [ ] **검증: `total_input == total_output`**
  ```python
  assert total_input == total_output, \
      f"조각 수 불일치: 입력 {total_input} vs 출력 {total_output}"
  ```

- [ ] **실패 시**: 어떤 조각이 누락/중복되었는지 상세 확인

**사례:** Multi-Tier 버그 #1에서 10 != 8 발견했어야 함

#### b) 크기별 조각 수 검증

**필수 확인:**
- [ ] **입력 크기별 개수 집계**
  ```python
  input_sizes = {}
  for w, h, count in pieces:
      input_sizes[(w, h)] = input_sizes.get((w, h), 0) + count
  ```

- [ ] **출력 크기별 개수 집계**
  ```python
  output_sizes = {}
  for plate in plates:
      for piece in plate['pieces']:
          key = (piece['width'], piece['height'])
          output_sizes[key] = output_sizes.get(key, 0) + 1
  ```

- [ ] **검증: 각 크기별로 `input_sizes == output_sizes`**
  ```python
  for size, count in input_sizes.items():
      output_count = output_sizes.get(size, 0)
      assert output_count == count, \
          f"크기 {size}: 입력 {count}개 vs 출력 {output_count}개"
  ```

**사례:** Multi-Tier 버그 #1에서 800×300: 5개 입력 vs 8개 출력 발견했어야 함

#### c) 조각 크기 정확성

- [ ] **모든 조각의 너비/높이가 정확한지** (±1mm 허용)
  ```python
  for plate in plates:
      for piece in plate['pieces']:
          # 회전되지 않은 경우
          if not piece.get('rotated'):
              assert piece['width'] == expected_width
              assert piece['height'] == expected_height
  ```

- [ ] **회전 옵션 적용 시 너비/높이 올바르게 바뀌었는지**
  ```python
  if piece.get('rotated'):
      assert piece['width'] == original_height
      assert piece['height'] == original_width
  ```

#### d) 조각 위치 유효성

- [ ] **모든 조각이 원판 경계 내부에 있는지**
  ```python
  for piece in plate['pieces']:
      assert 0 <= piece['x'] < plate_width
      assert 0 <= piece['y'] < plate_height
      assert piece['x'] + piece['width'] <= plate_width
      assert piece['y'] + piece['height'] <= plate_height
  ```

- [ ] **조각 간 겹침 없는지** (kerf 고려)
  - 모든 조각 쌍에 대해 겹침 확인
  - kerf 간격 확보 확인

### 4.2 시각적 검증 (Visual Verification)

#### a) PNG 이미지 생성 및 확인

- [ ] **모든 원판의 PNG 생성**
  ```bash
  ls -la *.png
  ```

- [ ] **⚠️ 이미지 파일 열어서 육안 검증 필수**
  - 파일 생성만으로는 부족!
  - 실제로 이미지를 열어서 확인해야 함
  - 운영체제 이미지 뷰어로 확인

#### b) 절단선 확인

**불필요한 절단선 확인:**
- [ ] **다른 행 사이 불필요한 group_boundary 없는지**
  - Multi-Tier 버그 #2 사례: 행이 다른 조각들 사이 경계선

- [ ] **빈 공간에 불필요한 trim 없는지**
  - 조각이 없는 곳의 trim 절단선

**누락된 절단선 확인:**
- [ ] **각 행의 우측 trim 존재하는지**
  - Multi-Tier 버그 #3 사례: Row 1 우측 trim 누락
  - 모든 행의 마지막 조각 우측에 trim 있어야 함

- [ ] **영역 경계 절단선 존재하는지**
  - 영역 간 분리선 확인

- [ ] **Tier boundary 절단선 존재하는지** (다단 배치 시)
  - 행과 행 사이 수평 절단선

#### c) 조각 배치 시각 확인

- [ ] **조각들이 겹치지 않는지**
  - 육안으로 확인

- [ ] **조각이 원판 밖으로 나갔는지**
  - 경계선 넘어가는 조각 없는지

- [ ] **kerf 간격이 올바른지**
  - 모든 조각 사이 간격 확인
  - 일반적으로 5mm

#### d) 절단선 순서 확인

- [ ] **priority 순서가 올바른지**
  - 영역 경계 (priority 1)
  - Tier 경계 (priority 낮음)
  - 그룹 경계
  - 조각 분리

- [ ] **절단선 번호(order)가 연속적인지**
  - 1, 2, 3, ... 순서대로
  - 누락된 번호 없는지

### 4.3 회귀 테스트 (Regression Tests)

#### a) 기존 테스트 케이스 실행

- [ ] **기본 프리셋 테스트** (800×310, 644×310, 371×270, 369×640)
  ```bash
  echo -e "2440\n1220\n5\ny\n800\n310\n2\n644\n310\n3\n371\n270\n4\n369\n640\n2\n0\n1\nn" | uv run woodcut
  ```
  - **예상**: 1판, 11/11 조각, 66.1% 사용률
  - **검증**: 결과가 정확히 일치하는지

- [ ] **회전 불허 테스트**
  ```bash
  echo -e "2440\n1220\n5\nn\n..." | uv run woodcut
  ```
  - **예상**: 회전 허용과 다른 결과
  - **검증**: 회전된 조각이 없는지

- [ ] **다양한 크기 조각 테스트**
  - 여러 프리셋으로 테스트
  - 이전 결과와 비교

#### b) 새 기능 OFF 시 동작 확인

- [ ] **새 옵션 비활성화 시 기존 결과와 동일한지**
  - 예: `enable_multi_tier=False`
  - 기존 동작 100% 보존 확인

- [ ] **옵션 미설정 시 기본 동작 유지되는지**
  - 기본값으로 테스트
  - 예상치 못한 변경 없는지

#### c) 성능 회귀 확인

- [ ] **실행 시간 비교** (급격한 증가 없는지)
  ```python
  import time
  start = time.time()
  plates = packer.pack(pieces)
  elapsed = time.time() - start
  print(f"실행 시간: {elapsed:.2f}초")
  ```
  - 이전 버전과 비교
  - 2배 이상 느려지면 검토 필요

### 4.4 제약 조건 검증 (Constraint Verification)

#### a) Guillotine Cut 제약

- [ ] **모든 절단선이 영역을 완전히 관통하는지**

  **수평선 확인:**
  ```python
  for cut in cuts:
      if cut['direction'] == 'H':
          assert cut['start'] == region_x
          assert cut['end'] == region_x + region_width
  ```

  **수직선 확인:**
  ```python
  for cut in cuts:
      if cut['direction'] == 'V':
          assert cut['start'] == region_y
          assert cut['end'] == region_y + region_height
  ```

- [ ] **부분 절단선 없는지**
  - 조각 일부만 자르는 선 없는지
  - 영역 중간에서 시작/끝나는 선 없는지

- [ ] **조각 중간을 자르는 절단선 없는지**
  - 모든 절단선이 조각 경계에 위치하는지

#### b) Kerf 고려

- [ ] **모든 조각 사이에 kerf 간격이 있는지**
  ```python
  # 인접 조각 간 최소 간격 확인
  for i, piece1 in enumerate(pieces):
      for piece2 in pieces[i+1:]:
          distance = calculate_distance(piece1, piece2)
          if distance > 0:  # 인접한 경우
              assert distance >= kerf
  ```

- [ ] **조각 크기 계산 시 kerf 포함되었는지**
  - 그룹 너비 계산: `count * width + (count - 1) * kerf`

#### c) 회전 제약

- [ ] **`allow_rotation=False` 시 회전된 조각 없는지**
  ```python
  if not allow_rotation:
      for plate in plates:
          for piece in plate['pieces']:
              assert not piece.get('rotated', False)
  ```

- [ ] **회전 시 너비/높이 올바르게 바뀌었는지**
  ```python
  if piece.get('rotated'):
      assert piece['width'] == original_height
      assert piece['height'] == original_width
  ```

### 4.5 엣지 케이스 검증

- [ ] **조각 1개만 있을 때**
  ```python
  pieces = [(800, 300, 1)]
  plates = packer.pack(pieces)
  assert len(plates) == 1
  assert len(plates[0]['pieces']) == 1
  ```

- [ ] **모든 조각 같은 크기일 때**
  ```python
  pieces = [(500, 500, 10)]
  plates = packer.pack(pieces)
  # 그룹화가 올바르게 작동하는지
  ```

- [ ] **조각이 원판보다 클 때** (오류 처리)
  ```python
  pieces = [(3000, 2000, 1)]  # 원판보다 큼
  # 적절한 오류 메시지 또는 경고 발생하는지
  ```

- [ ] **빈 입력일 때**
  ```python
  pieces = []
  plates = packer.pack(pieces)
  assert len(plates) == 0
  ```

- [ ] **매우 많은 조각** (100개+)
  ```python
  pieces = [(200, 200, 100)]
  plates = packer.pack(pieces)
  # 성능 저하 없는지, 정확성 유지되는지
  ```

---

## 5. 버그 사례 분석

> Multi-Tier Placement 구현 중 발견된 3가지 버그를 통해 체크리스트의 중요성을 이해합니다.

### 버그 #1: 조각 수 불일치 (10개 vs 8개)

#### 상황
```
입력: 800×300 (5개), 1800×300 (2개), 1800×800 (1개) = 8개
출력: 원판 1에 8개, 원판 2에 2개 = 10개
문제: 조각 수 불일치 (8개 입력 → 10개 배치)
```

#### 근본 원인
```python
# 문제 코드
extra_row = self._try_add_tier(
    remaining_pieces,  # ← 현재 plate 조각도 포함!
    width,
    height
)
```

- `_try_add_tier(remaining_pieces, ...)` 호출 시
- `remaining_pieces`가 현재 plate의 조각도 포함
- 다단 배치가 현재 plate 조각을 "추가"로 배치
- 결과: 동일 조각이 2번 배치됨

#### 놓친 검증 단계
- ❌ **4.1.a 수치 검증 안 함** (total_input == total_output)
- ❌ **4.1.b 크기별 개수 검증 안 함**

#### 체크리스트 적용 시
- ✅ **4.1.a에서 즉시 발견**: 10 != 8
- ✅ **4.1.b에서 즉시 발견**: 800×300: 8개 출력 vs 5개 입력

#### 교훈
> **수치 검증은 필수다!**
> 코드가 복잡해질수록 눈으로 확인하기 어렵다.
> 간단한 assert 문 하나가 몇 시간의 디버깅을 절약한다.

#### 수정 코드
```python
# 현재 plate 조각 필터링
placed_in_plate = {}
for p in plate['pieces']:
    size_key = (p['width'], p['height'])
    placed_in_plate[size_key] = placed_in_plate.get(size_key, 0) + 1

filtered_remaining = []
for piece in remaining_pieces:
    size_key = (piece['width'], piece['height'])
    if size_key in placed_in_plate and placed_in_plate[size_key] > 0:
        placed_in_plate[size_key] -= 1
    else:
        filtered_remaining.append(piece)

# 필터링된 조각으로 다단 배치 시도
extra_row = self._try_add_tier(filtered_remaining, width, height)
```

---

### 버그 #2: 불필요한 절단선 (9개 vs 7-8개)

#### 상황
```
Cut #4: Horizontal 300mm (불필요)
Cut #5: ... (불필요)
→ 다른 행 사이 불필요한 group_boundary 생성됨
```

#### 근본 원인
```python
# 문제 코드
sorted_pieces = sorted(placed, key=lambda p: p['x'])  # x만 정렬!
# → y 위치가 다른 조각들(다른 행)이 같은 그룹에 혼재
```

- 조각 정렬 시 x 좌표만 고려
- y 위치가 다른 조각들(다른 행)이 섞임
- group_boundary, trim 절단선이 다른 행 사이에 생성됨

#### 놓친 검증 단계
- ❌ **4.2.a PNG 이미지 확인 안 함**
- ❌ **4.2.b 불필요한 절단선 확인 안 함**

#### 체크리스트 적용 시
- ✅ **4.2.a PNG 열어보면 즉시 발견**: 이상한 수평선 보임
- ✅ **4.2.b 다른 행 사이 group_boundary 발견**

#### 교훈
> **PNG 확인은 필수다!**
> 파일 생성만으로는 부족하다.
> 실제로 이미지를 열어서 육안으로 확인해야 한다.
> 사람의 눈은 패턴 인식에 탁월하다.

#### 수정 코드
```python
# y 위치도 고려한 정렬
sorted_pieces = sorted(placed, key=lambda p: (p['y'], p['x']))

# y 위치 + 높이로 그룹 분할
groups = []
curr_group = {'pieces': [sorted_pieces[0]], 'height': None, 'y': sorted_pieces[0]['y']}

for i, piece in enumerate(sorted_pieces):
    piece_h = piece['width'] if piece.get('rotated') else piece['height']
    piece_y = piece['y']

    if i > 0:
        prev_y = sorted_pieces[i-1]['y']
        prev_h = sorted_pieces[i-1]['width'] if sorted_pieces[i-1].get('rotated') else sorted_pieces[i-1]['height']

        # y 위치가 다르거나 높이가 다르면 새 그룹
        if abs(piece_y - prev_y) > 1 or abs(piece_h - prev_h) > 1:
            groups.append(curr_group)
            curr_group = {'pieces': [piece], 'height': piece_h, 'y': piece_y}
        else:
            curr_group['pieces'].append(piece)
```

---

### 버그 #3: 누락된 trim 절단선

#### 상황
```
Row 1 (y=0~805): 5개 조각, 우측 trim 없음 ← 버그!
Row 2 (y=805~): 2개 조각, 우측 trim 있음
```

#### 근본 원인
```python
# 문제 코드
if group_idx == len(groups) - 1:  # 마지막 그룹만 체크
    # right_trim 생성
```

- 마지막 그룹만 체크
- 각 행의 마지막 그룹은 체크 안 함
- Row 1 마지막 그룹은 전체 마지막이 아니므로 trim 생성 안 됨

#### 놓친 검증 단계
- ❌ **4.2.a PNG 이미지 확인 안 함**
- ❌ **4.2.b 누락된 절단선 확인 안 함**

#### 체크리스트 적용 시
- ✅ **4.2.a PNG 열어보면 즉시 발견**: Row 1 우측에 절단선 없음
- ✅ **4.2.b 각 행의 right_trim 체크하면 발견**

#### 교훈
> **시각적 검증은 코드 검증을 보완한다!**
> 로직이 복잡할수록 시각적 확인이 중요하다.
> 특히 다단 구조에서는 각 행별 검증이 필요하다.

#### 수정 코드
```python
# 행 끝 판단: 마지막 그룹이거나, 다음 그룹이 다른 행일 때
is_row_end = (group_idx == len(groups) - 1)

if not is_row_end and group_idx < len(groups) - 1:
    next_group_y = groups[group_idx + 1]['y']
    if abs(next_group_y - group['y']) > 1:
        is_row_end = True  # 다음 그룹이 다른 행 → 현재 행 끝

if is_row_end:
    # right_trim 생성
    region_x_end = region['x'] + region['width']
    if region_x_end - last_x_end > self.kerf:
        cuts.append({
            'direction': 'V',
            'position': last_x_end,
            'start': group['y'],
            'end': group['y'] + group_h,
            'priority': priority_base,
            'type': 'right_trim',
            'sub_priority': 2
        })
```

---

## 6. 성공 선언 기준

### 6.1 필수 조건 (ALL must pass)

**✅ 성공 선언 가능:**

모든 항목이 체크되어야 합니다:

- ✅ **4.1 수치 검증 모두 통과**
  - 조각 수 일치
  - 크기별 개수 일치
  - 조각 크기 정확성
  - 조각 위치 유효성

- ✅ **4.2 시각적 검증 모두 통과**
  - PNG 이미지 육안 확인 완료
  - 불필요한 절단선 없음
  - 누락된 절단선 없음
  - 조각 배치 정상

- ✅ **4.3 회귀 테스트 모두 통과**
  - 기존 테스트 케이스 통과
  - 새 기능 OFF 시 기존 동작 유지
  - 성능 회귀 없음

- ✅ **4.4 제약 조건 검증 모두 통과**
  - Guillotine Cut 준수
  - Kerf 고려
  - 회전 제약 준수

- ✅ **4.5 엣지 케이스 검증 모두 통과**
  - 모든 경계 조건 처리 확인

**❌ 성공 선언 금지:**

다음 경우에는 절대 "성공"이라고 하지 마세요:

- ❌ 일부 테스트만 통과
- ❌ "대부분 잘 작동함"
- ❌ "작은 버그만 있음"
- ❌ PNG 확인 안 했음
- ❌ 수치 검증 안 했음
- ❌ 회귀 테스트 안 했음

### 6.2 부분 성공의 위험성

**잘못된 예시:**

```
❌ "조각 배치는 성공했습니다!"
→ 실제로는 10개 vs 8개 불일치 (버그 #1)

❌ "원판 수를 줄였습니다!"
→ 실제로는 불필요한 절단선 생성 (버그 #2)

❌ "다단 배치가 작동합니다!"
→ 실제로는 trim 절단선 누락 (버그 #3)

❌ "코드가 실행되니까 성공이에요!"
→ 실행되는 것과 올바른 것은 다릅니다

❌ "PNG 파일이 생성되었습니다!"
→ 파일 생성과 정확성은 별개입니다
```

**올바른 예시:**

```
✅ "체크리스트 4.1~4.5 모두 통과했습니다.

검증 결과:
- 4.1 수치 검증: 입력 8개 = 출력 8개 ✓
  - 800×300: 5개 ✓
  - 1800×300: 2개 ✓
  - 1800×800: 1개 ✓

- 4.2 시각적 검증: PNG 확인 완료 ✓
  - 절단선 8개 모두 필요 ✓
  - 불필요한 선 없음 ✓
  - 누락된 trim 없음 ✓

- 4.3 회귀 테스트: 통과 ✓
  - 기본 프리셋: 1판, 11/11 조각 ✓
  - 새 기능 OFF: 기존 동작 유지 ✓

- 4.4 제약 조건: Guillotine 준수 ✓
  - 모든 절단선 영역 관통 ✓
  - Kerf 간격 확보 ✓

- 4.5 엣지 케이스: 통과 ✓

따라서 구현이 성공적으로 완료되었습니다."
```

### 6.3 커밋 전 최종 확인

**체크리스트:**

- [ ] **모든 디버깅 로그 제거**
  ```bash
  grep -r "print(f\"DEBUG" src/
  # 결과 없어야 함
  ```

- [ ] **테스트 케이스 3개 이상 실행**
  - 기본 프리셋
  - 선반 프리셋
  - 커스텀 케이스

- [ ] **PNG 파일 최종 확인**
  - 모든 원판 이미지 확인
  - 이상 없음 확인

- [ ] **코드 리뷰 (본인)**
  - 불필요한 코드 제거
  - 주석 정리
  - 코드 스타일 통일

- [ ] **문서 업데이트** (PLAN.md 등)
  - 새 기능 설명 추가
  - 사용 예시 추가

**확인 후:**

```bash
git add .
git commit -m "feat: implement [기능명]

검증 완료:
- 조각 수 검증: 통과
- 시각적 검증: 통과
- 회귀 테스트: 통과
- 제약 조건: 통과
- 엣지 케이스: 통과

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## 7. 체크리스트 템플릿

> 이 템플릿을 복사해서 사용하세요!

```markdown
## 구현 검증 보고서

### 프로젝트: [기능명]
### 날짜: [YYYY-MM-DD]
### 구현자: [이름]

---

### 4.1 수치 검증

- [ ] 조각 수: 입력 ___ 개 = 출력 ___ 개
- [ ] 크기별 개수:
  - [ ] ___×___: 입력 ___ 개 = 출력 ___ 개
  - [ ] ___×___: 입력 ___ 개 = 출력 ___ 개
- [ ] 조각 크기 정확성: 모두 ±1mm 이내
- [ ] 조각 위치 유효성: 모두 원판 경계 내부

**결과:** ✅ 통과 / ❌ 실패

---

### 4.2 시각적 검증

- [ ] PNG 생성: 완료
- [ ] PNG 확인 (파일명: _____________): 육안 검증 완료
- [ ] 불필요한 절단선: 없음
  - [ ] 다른 행 사이 group_boundary: 없음
  - [ ] 빈 공간 trim: 없음
- [ ] 누락된 절단선: 없음
  - [ ] 각 행 우측 trim: 모두 존재
  - [ ] 영역 경계: 존재
  - [ ] Tier boundary (다단 시): 존재
- [ ] 조각 배치: 정상
  - [ ] 겹침: 없음
  - [ ] 경계 넘어감: 없음
  - [ ] Kerf 간격: 올바름

**결과:** ✅ 통과 / ❌ 실패

---

### 4.3 회귀 테스트

- [ ] 기본 프리셋: 1판, 11/11 조각, 66.1% 사용률
- [ ] 회전 불허: 결과 변경됨, 회전된 조각 0개
- [ ] 새 기능 OFF: 기존 동작 유지
- [ ] 성능: 이전 버전 대비 ___ 초 (2배 이하)

**결과:** ✅ 통과 / ❌ 실패

---

### 4.4 제약 조건 검증

- [ ] Guillotine Cut: 모든 절단선 영역 관통
- [ ] Kerf: 모든 조각 사이 ___mm 간격
- [ ] 회전 제약:
  - [ ] allow_rotation=True: 회전 가능
  - [ ] allow_rotation=False: 회전된 조각 0개

**결과:** ✅ 통과 / ❌ 실패

---

### 4.5 엣지 케이스

- [ ] 조각 1개: 정상 처리
- [ ] 같은 크기: 그룹화 정상
- [ ] 큰 조각: 오류 처리 또는 경고
- [ ] 빈 입력: 빈 결과
- [ ] 많은 조각 (100개): 정상 처리

**결과:** ✅ 통과 / ❌ 실패

---

### 최종 결과

- [ ] 모든 검증 통과
- [ ] 디버깅 로그 제거
- [ ] 문서 업데이트
- [ ] 커밋 메시지 작성

**결론:** ✅ 성공 / ❌ 실패

---

### 특이사항 및 비고

[여기에 특이사항 기록]
```

---

## 8. 자주 하는 실수

### 실수 #1: PNG 생성만 하고 확인 안 함

**잘못된 행동:**
```bash
ls -la *.png
# 파일 있네? 성공!
```

**올바른 행동:**
```bash
ls -la *.png
# 파일 확인
open *.png  # 또는 이미지 뷰어로 열기
# 육안으로 절단선, 조각 배치 확인
```

### 실수 #2: 총 조각 수만 체크, 크기별 개수 체크 안 함

**잘못된 검증:**
```python
total_input = 8
total_output = 8
# 같네? 성공!
```

**올바른 검증:**
```python
total_input = 8
total_output = 8  # 같음

# 하지만 크기별로 확인하면:
# 800×300: 입력 5개 vs 출력 8개 ← 버그!
# 1800×300: 입력 2개 vs 출력 0개 ← 버그!
```

### 실수 #3: 회전 허용만 테스트, 불허 테스트 안 함

**잘못된 테스트:**
```python
# 회전 허용만 테스트
allow_rotation = True
plates = packer.pack(pieces)
# 잘 되네? 성공!
```

**올바른 테스트:**
```python
# 회전 허용
allow_rotation = True
plates1 = packer.pack(pieces)

# 회전 불허
allow_rotation = False
plates2 = packer.pack(pieces)

# 두 결과가 달라야 함
# plates2에 rotated=True 조각 있으면 버그!
```

### 실수 #4: 정상 케이스만 테스트, 엣지 케이스 무시

**잘못된 테스트:**
```python
# 정상 케이스만
pieces = [(800, 300, 5), (600, 200, 3)]
plates = packer.pack(pieces)
# 잘 되네? 성공!
```

**올바른 테스트:**
```python
# 정상 케이스
pieces = [(800, 300, 5)]
assert len(packer.pack(pieces)) > 0

# 엣지 케이스
pieces = []  # 빈 입력
assert len(packer.pack(pieces)) == 0

pieces = [(3000, 2000, 1)]  # 원판보다 큰 조각
# 오류 처리 확인

pieces = [(100, 100, 200)]  # 매우 많은 조각
# 성능 확인
```

### 실수 #5: 로그 출력만 보고 판단, 시각화 확인 안 함

**잘못된 검증:**
```
=== 원판 1 ===
배치된 조각: 8개
절단선: 9개

# 숫자만 보고 성공!
```

**올바른 검증:**
```
=== 원판 1 ===
배치된 조각: 8개  # OK
절단선: 9개  # OK?

# PNG 확인
open plate_1.png
# → 어? Cut #4가 불필요한 선이네? 버그!
```

### 실수 #6: 부분 구현 후 조기 성공 선언

**잘못된 행동:**
```
"다단 배치 기능 구현했어요!"
# 실제로는 조각 수 불일치, 절단선 오류 있음
```

**올바른 행동:**
```
"다단 배치 기능 구현 완료
→ 검증 체크리스트 실행 중...
→ 4.1 수치 검증: 통과
→ 4.2 시각적 검증: 통과
→ 4.3 회귀 테스트: 통과
→ 4.4 제약 조건: 통과
→ 4.5 엣지 케이스: 통과
→ 모든 검증 통과! 성공!"
```

---

## 검증 프로세스 플로우차트

```
┌─────────────────────┐
│   구현 완료         │
└──────────┬──────────┘
           │
           ↓
┌──────────────────────────────────┐
│ 4.1 수치 검증                    │
│ - 조각 수 일치?                  │
│ - 크기별 개수 일치?              │
└──────────┬───────────────────────┘
           │ 통과
           ↓
┌──────────────────────────────────┐
│ 4.2 시각적 검증                  │
│ - PNG 확인했는가? ★              │
│ - 불필요한/누락된 절단선 없는가? │
└──────────┬───────────────────────┘
           │ 통과
           ↓
┌──────────────────────────────────┐
│ 4.3 회귀 테스트                  │
│ - 기존 기능 유지?                │
│ - 새 기능 OFF 시 동작?           │
└──────────┬───────────────────────┘
           │ 통과
           ↓
┌──────────────────────────────────┐
│ 4.4 제약 조건 검증               │
│ - Guillotine 준수?               │
│ - Kerf 고려?                     │
└──────────┬───────────────────────┘
           │ 통과
           ↓
┌──────────────────────────────────┐
│ 4.5 엣지 케이스                  │
│ - 특수 케이스 처리?              │
└──────────┬───────────────────────┘
           │ 모두 통과
           ↓
┌──────────────────────────────────┐
│ ✅ 성공 선언 가능                │
│ ✅ 커밋 가능                     │
└──────────────────────────────────┘

          실패 ←─────┐
           │         │
           ↓         │
┌──────────────────────────────────┐
│ 버그 수정                        │
│ → 다시 4.1부터 시작              │
│ → 절대 "부분 성공" 선언 금지     │
└──────────────────────────────────┘
```

---

## 결론

### 핵심 메시지

> **"구현 완료 ≠ 성공"**
> **"검증 완료 = 성공"**

### 필수 5단계 검증

1. **수치 검증** (조각 수, 크기별 개수)
2. **시각적 검증** (PNG 확인, 절단선 검증)
3. **회귀 테스트** (기존 기능 유지)
4. **제약 조건 검증** (Guillotine, Kerf)
5. **엣지 케이스 테스트**

→ **5단계 모두 통과 후에만 "성공" 선언 가능**

### 이 문서를 사용하는 방법

1. **구현 전**: 섹션 2 읽기
2. **구현 중**: 섹션 3 참고하며 진행
3. **구현 후**: 섹션 4 체크리스트 실행 ★★★
4. **성공 선언 전**: 섹션 6 기준 확인
5. **커밋 전**: 섹션 7 템플릿 작성

### 기대 효과

- ✅ 사용자 지적 전 자체 버그 발견
- ✅ "성공" 조기 선언 방지
- ✅ 품질 향상 (체계적 검증)
- ✅ 시간 절약 (수정 반복 감소)
- ✅ 신뢰성 향상

---

**이 문서를 활용하여 모든 구현에 체계적인 검증을 적용하세요!**
