# 다단 배치(Multi-Tier Placement) 설계

> 작성 시작: 2026-01-04
> 상태: 계획 단계
> 관련 이슈: 향후 개선 #2

---

## 문제 분석

### 현재 방식의 한계

**단일 행(Single-Tier) 배치:**
```
영역 = 하나의 행
┌────────────────────────────────────────────┐
│ [조각1][조각2][조각3]                     │  ← 단일 행
│                                            │
│          (남은 공간 미활용)                │
└────────────────────────────────────────────┘

문제:
- 영역 높이 = max(조각 높이들)
- 남은 세로 공간 활용 불가
- 공간 활용률 제한 (~66%)
```

### 실제 예시

```python
# 큰 조각 영역
영역 1: 310mm 높이 (조각들: 644×310, 644×310, 644×310)
→ 원판 높이 1220mm - 310mm = 910mm 남음

# 작은 조각들
남은 조각: 200×100 (5개)
→ 다음 판으로 넘어가거나 배치 불가
```

**결과**: 공간 낭비 + 추가 판 필요 가능성

---

## 해결책: 옵션 기반 다단 배치

### 핵심 아이디어

**다중 행(Multi-Tier) 배치:**
```
영역 = 여러 행의 조합
┌────────────────────────────────────────────┐
│ [조각1][조각2]                            │  ← 1행 (큰 조각)
├────────────────────────────────────────────┤
│ [조각3][조각4][조각5]                     │  ← 2행 (작은 조각)
│                                            │
└────────────────────────────────────────────┘

효과:
- 남은 세로 공간 활용
- 공간 활용률 향상 (66% → 70-75%)
- 판 수 감소 가능
```

### 설계 원칙

#### 1. 옵션 기반 (Opt-in)
```python
enable_multi_tier = False  # 기본값: OFF
```
- 기본 동작 변경 없음
- 명시적 활성화 시에만 작동
- 하위 호환성 보장

#### 2. 보수적 적용 (Conservative)
```python
# 조건 1: 남은 공간이 충분할 때만
if remaining_height > 100mm:

# 조건 2: 작은 조각만
if piece_height < existing_height * 0.5:

# 조건 3: 활용률이 높을 때만
if utilization > 0.8:
```
- 확실한 이득이 있을 때만
- 강제하지 않음
- 실패 시 기존 방식 유지

#### 3. Guillotine 준수
```
각 행은 수평 절단선으로 완전 분리:

수평 ━━━━━━━━━━━━━━━━ (1행 하단)
      [1행 조각들]
수평 ━━━━━━━━━━━━━━━━ (2행 하단)
      [2행 조각들]
수평 ━━━━━━━━━━━━━━━━ (영역 하단)
```

---

## 구현 상세

### 1. 데이터 구조 확장

#### Before (단일 행)
```python
region = {
    'type': 'horizontal',
    'groups': [...],  # 직접 그룹 저장
    'x': 0,
    'y': 0,
    'width': 2440,
    'height': 374     # 단일 높이
}
```

#### After (다중 행)
```python
region = {
    'type': 'horizontal',
    'rows': [                          # 행 리스트
        {
            'groups': [...],
            'height': 374
        },
        {
            'groups': [...],  # 추가 행
            'height': 120
        }
    ],
    'x': 0,
    'y': 0,
    'width': 2440,
    'height': 494      # 총 높이 (374 + 120)
}
```

**호환성 유지:**
- 옵션 OFF 시: rows[0]만 사용 (기존과 동일)
- 옵션 ON 시: rows[1..n] 추가

### 2. 남은 공간 탐지

**파일**: `src/woodcut/strategies/region_based.py`

```python
def _detect_remaining_space(self, region):
    """영역의 남은 세로 공간 계산

    Args:
        region: 영역 딕셔너리

    Returns:
        (width, height, y_offset) or None
    """
    # 첫 행의 높이
    used_height = region['rows'][0]['height']

    # 남은 높이
    region_bottom = region['y'] + used_height
    plate_bottom = self.plate_height
    remaining = plate_bottom - region_bottom

    # Threshold 체크 (기본 100mm)
    if remaining > self.multi_tier_threshold:
        return (
            region['width'],     # 가용 너비
            remaining,           # 가용 높이
            region_bottom        # y 시작점
        )

    return None
```

### 3. 보수적 추가 행 생성

```python
def _try_add_tier(self, remaining_pieces, width, height, existing_height):
    """보수적으로 추가 행 배치 시도

    Args:
        remaining_pieces: 남은 조각들
        width: 가용 너비
        height: 가용 높이
        existing_height: 기존 행 높이 (비교용)

    Returns:
        새 행 딕셔너리 or None
    """
    # 조건 1: 작은 조각만 후보
    #   - 높이가 가용 공간에 맞음
    #   - 기존 행 높이의 50% 미만 (작은 조각)
    candidates = [
        p for p in remaining_pieces
        if p['height'] <= height
        and p['height'] < existing_height * 0.5
    ]

    if not candidates:
        return None

    # 조건 2: 같은 높이끼리 그룹화
    groups = self._group_by_exact_size(candidates)

    # 조건 3: 활용률 80% 이상인 그룹 찾기
    for group in groups:
        # 그룹을 한 행에 배치했을 때 활용률
        total_width = group['size'][0] * group['count']  # 조각들의 총 너비
        total_width += self.kerf * (group['count'] - 1)  # kerf 포함

        utilization = total_width / width

        if utilization >= 0.8:
            # 충분한 활용률 → 새 행 생성
            return {
                'groups': [group],
                'height': group['size'][1] + self.kerf  # kerf 포함
            }

    return None
```

### 4. 백트래킹 통합

**수정 위치**: `pack()` 메서드

```python
def pack(self, pieces):
    # ... 기존 그룹화 및 백트래킹 ...

    regions = self._allocate_anchor_backtrack(all_variants)

    # ★ 다단 배치 옵션이 켜진 경우
    if self.enable_multi_tier and remaining_pieces:
        print("\n=== 다단 배치 시도 ===")

        for region in regions:
            # 남은 공간 탐지
            space = self._detect_remaining_space(region)

            if space:
                width, height, y_offset = space
                existing_h = region['rows'][0]['height']

                print(f"영역 {region['id']}: 남은 {height}mm 탐지")

                # 보수적 추가 행 시도
                extra_row = self._try_add_tier(
                    remaining_pieces,
                    width,
                    height,
                    existing_h
                )

                if extra_row:
                    # 추가 행 배치
                    region['rows'].append(extra_row)
                    region['height'] += extra_row['height']

                    # remaining_pieces 업데이트
                    placed_count = sum(
                        g['count'] for g in extra_row['groups']
                    )
                    print(f"  → 추가 행 배치: {placed_count}개 조각")

                    # 배치된 조각 제거
                    self._remove_placed_pieces(remaining_pieces, extra_row)
                else:
                    print(f"  → 조건 불충족, 스킵")

    # ... 나머지 로직 ...
```

### 5. 절단선 생성 확장

**수정**: `_pack_multi_group_region()`

```python
def _pack_multi_group_region(self, region, region_id, region_index,
                             is_first_region, is_last_region,
                             region_priority_base):
    placed = []
    cuts = []

    # 영역 경계 (Tier 1)
    if not is_first_region:
        cuts.append({
            'direction': 'H',
            'position': region['y'],
            'priority': region_index,
            'type': 'region_boundary'
        })

    # ★ 다중 행 처리
    current_y = region['y']

    for row_idx, row in enumerate(region['rows']):
        # 행 경계 절단 (첫 행 제외)
        if row_idx > 0:
            cuts.append({
                'direction': 'H',
                'position': current_y,
                'priority': region_priority_base + 5 + row_idx,
                'sub_priority': 0,
                'type': 'tier_boundary'
            })

        # 행 내 조각 배치 및 절단 (기존 로직)
        for group in row['groups']:
            # ... 그룹별 배치 ...
            # ... 조각 분리 절단선 ...
            # ... 그룹 경계 절단선 ...
            pass

        # 다음 행 시작 y 업데이트
        current_y += row['height']

    return placed, cuts
```

### 6. CLI 인터페이스

**파일**: `src/woodcut/interactive.py`

```python
def run_interactive():
    # ... 기존 입력 ...

    # 다단 배치 옵션 추가
    print("\n[다단 배치]")
    print("남은 공간에 작은 조각 추가 배치 (보수적)")
    enable_multi_tier_input = input("활성화? (y/n, 기본: n): ").strip().lower()
    enable_multi_tier = enable_multi_tier_input == 'y'

    # RegionBasedPacker 생성
    packer = RegionBasedPacker(
        plate_width,
        plate_height,
        kerf,
        allow_rotation,
        enable_multi_tier=enable_multi_tier  # ★ 새 파라미터
    )
```

---

## 검증 계획

### 테스트 케이스 1: 다단 비활성화

```python
pieces = [
    (800, 310, 2),
    (644, 310, 3),
    (371, 270, 4),
    (369, 640, 2)
]
enable_multi_tier = False
```

**예상 결과:**
- 현재와 100% 동일
- 11/11 조각 배치
- 1판, 66.1% 사용률
- 15개 절단선

**검증:**
- ✅ 기존 동작 보존
- ✅ 코드 경로 변경 없음

### 테스트 케이스 2: 다단 활성화 (이득 없음)

```python
pieces = [(800, 310, 5)]  # 큰 조각만
enable_multi_tier = True
```

**예상 결과:**
- 추가 행 없음 (작은 조각이 없으므로)
- 기존과 동일한 배치

**검증:**
- ✅ 조건 불충족 시 안전하게 스킵
- ✅ 강제하지 않음

### 테스트 케이스 3: 다단 활성화 (이득 있음)

```python
pieces = [
    (800, 310, 2),   # 큰 조각 (310mm 높이)
    (200, 100, 5)    # 작은 조각 (100mm 높이)
]
enable_multi_tier = True
```

**예상 결과:**
```
영역 1:
  - 1행: 800×310 (2개) → 높이 315mm (kerf 포함)
  - 남은 공간: 1220 - 315 = 905mm
  - 2행: 200×100 (5개) → 높이 105mm (kerf 포함)

총 사용률: 향상 (1판에 모두 배치)
```

**검증:**
- ✅ 남은 공간 활용
- ✅ 공간 활용률 증가
- ✅ Guillotine 절단 순서 준수

---

## 예상 효과

### 공간 활용률
- **현재**: ~66% (단일 행)
- **개선**: ~70-75% (케이스별 다름)
- **조건**: 큰 조각 + 작은 조각 혼합 시

### 코드 변경
- **추가 코드**: ~200줄
- **복잡도**: 중간 (옵션 분기로 제어)
- **기존 영향**: 없음 (옵션 OFF 시)

### 안정성
- **보수적 조건**: 3가지 (공간, 크기, 활용률)
- **Guillotine 보장**: 각 행은 수평 절단선으로 분리
- **하위 호환**: 100% (기본 OFF)

---

## 위험 요소 및 대응

### 위험 1: Guillotine 위반
**시나리오**: 행 경계가 불완전하게 절단됨

**대응:**
- 각 행은 반드시 완전 관통 수평 절단선으로 분리
- Priority 시스템에 `tier_boundary` 타입 추가
- 절단선 생성 시 영역 전체 너비 확인

### 위험 2: 복잡도 증가
**시나리오**: 다단 로직이 기존 코드를 복잡하게 만듦

**대응:**
- 옵션 OFF 시 기존 코드 경로 유지 (if 분기)
- 다단 로직을 별도 메서드로 분리 (`_try_add_tier`)
- 명확한 주석 및 로깅

### 위험 3: 디버깅 어려움
**시나리오**: 다단 배치 시 버그 추적 어려움

**대응:**
- 상세 로깅 추가
  ```python
  print(f"[다단] 영역 {id}: 남은 {h}mm, 시도 중...")
  print(f"[다단] → 추가 행 배치: {count}개")
  ```
- 단계별 검증 (테스트 케이스 3개)
- 시각화로 결과 확인

---

## 구현 순서

1. ✅ **계획 수립** (이 문서)
2. ⬜ 데이터 구조 확장 (`region['rows']`)
3. ⬜ `_detect_remaining_space()` 구현
4. ⬜ `_try_add_tier()` 구현
5. ⬜ `pack()` 메서드에 다단 로직 통합
6. ⬜ `_pack_multi_group_region()` 다중 행 처리
7. ⬜ CLI 옵션 추가 (`interactive.py`)
8. ⬜ 테스트 케이스 3개 검증
9. ⬜ 문서 업데이트 (PLAN.md, ALGORITHM.md)

---

## 참고

### 관련 문서
- [PLAN.md](../PLAN.md) - 프로젝트 전체 계획
- [ALGORITHM.md](../ALGORITHM.md) - 알고리즘 상세
- [001: Guillotine 절단 통합](./001-20251231-guillotine-cutting-integration.md)

### 버전
- 타겟 버전: v0.4.0
- 작성일: 2026-01-04
