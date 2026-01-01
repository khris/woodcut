# Woodcut - 목재 재단 최적화 프로젝트

## 프로젝트 개요

목재 재단 최적화를 위한 Guillotine Cut 알고리즘 구현

- **목표**: 원판에서 필요한 조각들을 효율적으로 배치하고 절단 순서 생성
- **제약사항**: Guillotine Cut (영역 전체를 관통하는 직선 절단만 가능)
- **입력**: 원판 크기, 조각 목록, 톱날 두께(kerf), 회전 허용 여부
- **출력**: 배치 계획, 절단 순서, 시각화 이미지

---

## 현재 구현 상태

### 패킹 전략

**RegionBasedPacker (영역 기반 패킹)** - 유일한 전략

핵심 개념:
- **다중 그룹 영역 배치**: 한 영역에 여러 그룹 배치 (1:N 매핑)
- **그룹화**: 정확히 같은 크기의 조각들끼리 그룹화
- **호환 세트 생성**: 높이/너비가 비슷한 그룹들을 묶어서 영역 후보 생성
- **백트래킹 최적화**: 모든 그룹을 배치할 수 있는 최적의 영역 조합 탐색
- **다중 판 지원**: 한 판에 들어가지 않는 조각들은 다음 판에 배치

### Guillotine Cut 알고리즘 (통합형 배치+절단)

**핵심 개념: 배치와 절단 통합**
- ~~FSM 기반 2-Phase 재귀 (삭제됨)~~
- 영역 배치 시 절단선도 함께 생성
- 우선순위 시스템으로 길로틴 원칙 준수

**절단선 우선순위 시스템:**
```python
priority 1: 영역 경계 (수평) + 자투리 영역 경계
  - position 순으로 정렬 (위→아래)
  - 길로틴 원칙: 완전 관통 절단이 최우선

priority 2: 영역 상단 자투리 trim (수평)
priority 3: 그룹 경계 (수직)
priority 4: 그룹별 개별 trim (수평)
priority 5: 조각 분리 (수직, sub_priority=1)
         + 우측 자투리 trim (수직, sub_priority=2)

정렬키: (priority, region_index, sub_priority, position)
  - Priority 1: position만 고려 (영역 경계 위→아래)
  - Priority 2-5: region_index → sub_priority → position
                 (한 영역 완료 후 다음 영역)
```

**자투리 영역 처리:**
- 상단 자투리: 백트래킹 완료 후 별도 scrap 영역으로 추가
- scrap 영역은 조각 없이 경계 절단선만 생성
- kerf보다 크면 무조건 처리 (10mm 임계값 제거)

---

## 핵심 알고리즘 상세

### 1. 다중 그룹 영역 배치

```python
def pack(self, pieces):
    while remaining_pieces:
        # 1. 레벨 1: 정확히 같은 크기끼리 그룹화
        groups = self._group_by_exact_size(remaining_pieces)

        # 2. 각 그룹의 회전 옵션 생성
        group_options = self._generate_group_options(groups)

        # 3. 호환 가능한 그룹 세트 생성 (tolerance=100mm)
        group_sets = self._generate_compatible_group_sets(group_options)

        # 4. 백트래킹으로 최적 조합 찾기
        regions = self._allocate_multi_group_backtrack(group_sets)

        # 5. 각 영역 내 배치 + 절단선 생성 (통합)
        all_cuts = []
        for i, region in enumerate(regions):
            placed, cuts = self._pack_multi_group_region(
                region, region_index=i, is_first_region=(i==0)
            )
            if placed:
                plate['pieces'].extend(placed)
            if cuts:
                for cut in cuts:
                    cut['region_index'] = i
                all_cuts.extend(cuts)

        # 6. 절단선 우선순위 정렬
        all_cuts.sort(key=sort_key)  # (priority, region_index, sub_priority, position)
        plate['cuts'] = all_cuts

        # 7. 배치된 조각 제거, 다음 판으로
        remaining_pieces = [...]
```

**특징:**
- 높이 차이가 100mm 이내인 그룹들을 같은 영역에 배치 가능
- 하단 정렬(bottom-alignment)로 높이 차이 처리
- 그룹 단위 회전으로 작업 편의성 확보

### 2. 호환 그룹 세트 생성

```python
# 예시: 644×310 (3개) + 640×369 (2개, 회전)
{
    'type': 'horizontal',
    'max_height': 374,  # max(310, 369) + kerf
    'groups': [
        {'original_size': (644, 310), 'rotated': False, 'count': 3},
        {'original_size': (369, 640), 'rotated': True, 'count': 2}
    ],
    'total_area': 598920 + 472320
}
```

**생성 조건:**
1. 높이 차이가 `tolerance` 이내 (기본 100mm)
2. 너비 합계가 원판 너비 이내 (kerf 포함)
3. 단일 그룹 세트도 폴백용으로 추가

### 3. 백트래킹 영역 할당

```python
def backtrack(selected_sets, used_groups, y_offset):
    # 종료 조건: 모든 그룹 배치 완료
    if len(used_groups) == total_groups:
        return selected_sets, placed_count

    # 각 세트 시도
    for group_set in group_sets:
        # 1. 이미 사용된 그룹은 스킵
        if set_groups & used_groups:
            continue

        # 2. 공간 체크
        if y_offset + region_height > plate_height:
            continue

        # 3. 재귀 호출
        result_sets, result_count = backtrack(
            selected_sets + [region],
            used_groups | set_groups,
            y_offset + region_height
        )

        if result_count > best_count:
            best_count = result_count
            best_sets = result_sets

    return best_sets, best_count
```

**최적화:**
- 영역 세트를 면적순으로 정렬 (큰 세트 우선)
- 공간 부족 시 조기 가지치기
- 모든 그룹 배치 시 즉시 종료

### 4. 절단선 생성 알고리즘 상세

#### 통합형 배치+절단 방식

**기존 문제점 (삭제된 FSM):**
- 배치 단계와 절단 단계 분리로 정보 손실
- 재귀적 영역 분할이 조각을 분산시켜 절단선 누락
- 길로틴 원칙 위반 (부분 절단이 먼저 실행)

**새로운 방식:**
- `_pack_multi_group_region()` 함수가 배치와 절단을 동시 수행
- 배치 과정에서 이미 알고 있는 정보 (그룹 경계, kerf 간격)로 절단선 직접 생성
- 우선순위 시스템으로 길로틴 원칙 보장

#### 영역별 절단선 생성 로직

```python
def _pack_multi_group_region(self, region, region_id, region_index,
                             is_first_region, is_last_region):
    cuts = []

    # 자투리 영역 처리
    if region['type'] == 'scrap':
        if not is_first_region:
            cuts.append({'priority': 1, 'type': 'scrap_boundary', ...})
        return placed, cuts

    # Priority 1: 영역 경계 (첫 영역 제외)
    if not is_first_region:
        cuts.append({'priority': 1, 'type': 'region_boundary', ...})

    # Priority 2: 영역 상단 자투리 trim
    if abs(max_required_h - max_height) > 1:
        cuts.append({'priority': 2, 'type': 'region_trim', ...})

    # Priority 3: 그룹 경계 절단
    if abs(curr_h - next_h) > 1:
        cuts.append({'priority': 3, 'type': 'group_boundary', ...})

    # Priority 4: 그룹별 개별 trim
    if abs(left_h - max_required_h) > 1:
        cuts.append({'priority': 4, 'type': 'group_trim', ...})

    # Priority 5: 조각 분리 + 우측 자투리 (sub_priority로 구분)
    for i in range(len(sorted_pieces) - 1):
        if i != group_boundary_idx:
            cuts.append({'priority': 5, 'sub_priority': 1,
                        'type': 'piece_separation', ...})

    if region_x_end - last_x_end > self.kerf:
        cuts.append({'priority': 5, 'sub_priority': 2,
                    'type': 'right_trim', ...})

    return placed, cuts
```

#### 우선순위 정렬 및 길로틴 순서 보장

```python
def sort_key(cut):
    priority = cut.get('priority', 100)
    region_idx = cut.get('region_index', 0)
    sub_priority = cut.get('sub_priority', 0)
    position = cut.get('position', 0)

    if priority == 1:
        # 영역 경계: position만 고려 (위→아래 순)
        return (priority, position, 0, 0)
    else:
        # 영역 내부: region_index → sub_priority → position
        # 한 영역 완료 후 다음 영역
        return (priority, region_idx, sub_priority, position)
```

**결과:**
- 영역 경계(priority 1) 모두 먼저 실행 → 길로틴 원칙 준수
- 각 영역별로 절단 완료 후 다음 영역 진행
- 조각 분리와 우측 trim이 같은 영역 내에서 혼합 실행

---

## 알고리즘 동작 예시

### 실제 테스트 케이스 (11개 조각)

**입력:**
```python
pieces = [
    (800, 310, 2),   # 800×310mm 2개
    (644, 310, 3),   # 644×310mm 3개
    (371, 270, 4),   # 371×270mm 4개
    (369, 640, 2),   # 369×640mm 2개 (회전 가능)
]
```

**백트래킹 결과:**
- 영역 0: 640×369 (2개, 회전) + 270×371 (4개, 회전)
- 영역 1: 644×310 (3개)
- 영역 2: 800×310 (2개)
- 영역 3 (scrap): 상단 자투리 (214mm)

**절단 순서 (15개):**

```
Priority 1 (영역 경계):
1. 수평  376mm  (영역0→영역1 경계)
2. 수평  691mm  (영역1→영역2 경계)
3. 수평 1006mm  (영역2→자투리 경계)

Priority 2-5 (영역0 처리):
4. 수직 1285mm  (그룹 경계: 640×369 | 270×371)
5. 수평  369mm  (좌측 그룹 trim)
6. 수직  640mm  (조각 분리)
7. 수직 1285mm  (조각 분리)
8. 수직 1605mm  (우측 자투리 trim)

Priority 2-5 (영역1 처리):
9. 수직  644mm  (조각 분리)
10. 수직 1293mm  (조각 분리)
11. 수직 1942mm  (우측 자투리 trim)

Priority 2-5 (영역2 처리):
12. 수직  800mm  (조각 분리)
13. 수직 1560mm  (조각 분리)
14. 수직 1835mm  (조각 분리)
15. 수직 2385mm  (우측 자투리 trim)
```

**핵심 특징:**
- ✅ 길로틴 원칙 준수: 영역 경계(1-3번)가 최우선 실행
- ✅ 영역별 완료: 영역0 → 영역1 → 영역2 순차 처리
- ✅ 자투리 처리: 상단 자투리 영역 + 각 영역 우측 trim
- ✅ 조각 분리와 trim 혼합: 같은 priority 5 내에서 sub_priority로 구분

---

## 주요 개념 정리

### Guillotine Cut
- **정의**: 영역 전체를 관통하는 직선 절단
- **제약**: 부분적인 절단 불가 (한쪽 끝에서 반대쪽 끝까지 완전히 관통)
- **장점**: 실제 재단 작업에서 구현 가능
- **단점**: 공간 활용률이 다소 낮을 수 있음

### placed_w / placed_h vs width / height
- **width / height**: 조각의 원본 크기 (회전 전)
- **placed_w / placed_h**: 배치 시 실제 차지하는 크기 (회전 후)
- **용도**: 절단 알고리즘이 이미 트림된 조각을 식별하는 데 사용

### Kerf (톱날 두께)
- **정의**: 톱날이 지나가면서 손실되는 재료의 두께
- **기본값**: 5mm
- **적용**: 모든 절단선과 조각 간격에 kerf 추가

### 회전 (Rotation)
- **허용 시**: 조각을 90도 회전 가능 (결이 없는 재질)
- **불허 시**: 조각 회전 불가 (결이 있는 재질)
- **구현**: 그룹 단위 회전 (같은 크기 조각들은 함께 회전)

---

## 삭제된 전략들 (개발 과정)

이전에는 6가지 전략이 있었으나, RegionBasedPacker만 남기고 모두 삭제:

1. **AlignedFreeSpacePacker** (정렬 우선 자유 공간)
   - 그리디 알고리즘
   - 정렬 점수 기반 배치

2. **GeneticAlignedFreeSpacePacker** (유전 알고리즘)
   - 유전 알고리즘 + AlignedFreeSpace 조합
   - 진화 기반 최적화

3. **BeamSearchPacker** (빔 서치)
   - 백트래킹 기반
   - beam_width=3

4. **LookAheadPacker** (룩어헤드)
   - 그룹화 휴리스틱
   - 미래 배치 고려

5. **GeneticGroupPreservingPacker** (그룹 보존 유전)
   - 그룹 기반 유전 알고리즘
   - 작업 편의성 고려

**삭제 이유:**
- RegionBasedPacker가 가장 발전된 알고리즘
- 다중 그룹 영역 배치 (1:N 매핑) 구현 완료
- 나머지는 개발 과정의 시행착오

---

## 테스트 결과

### 테스트 케이스
```python
pieces = [
    (800, 310, 2),   # 800×310mm 2개
    (644, 310, 3),   # 644×310mm 3개
    (371, 270, 4),   # 371×270mm 4개
    (369, 640, 2),   # 369×640mm 2개
]
# 총 11개 조각
```

### 회전 허용 결과
- **원판 수**: 1장
- **배치**: 11/11개 (100%)
- **사용률**: 66.1%
- **절단 횟수**: 15회 (길로틴 순서 준수)
- **영역**: 4개 (3개 조각 영역 + 1개 자투리 영역)
  - 영역 0: 640×369 (2개, 회전) + 270×371 (4개, 회전)
  - 영역 1: 644×310 (3개)
  - 영역 2: 800×310 (2개)
  - 영역 3 (scrap): 상단 자투리 (214mm)

### 회전 불허 결과
- **원판 수**: 2장
- **배치**: 11/11개 (100%)
- **원판 1**: 9개 (사용률 50.2%)
  - 644×310 (3개)
  - 800×310 (2개)
  - 371×270 (4개)
- **원판 2**: 2개 (사용률 15.9%)
  - 369×640 (2개)
- **총 절단 횟수**: 15회

---

## 프로젝트 구조

```
woodcut/
├── src/woodcut/
│   ├── __init__.py           # CLI 엔트리 포인트
│   ├── packing.py            # Guillotine Cut 알고리즘
│   ├── visualizer.py         # 시각화
│   └── strategies/
│       ├── __init__.py       # 전략 export
│       └── region_based.py   # RegionBasedPacker
├── output/                   # 시각화 출력 (gitignore)
├── pyproject.toml           # 프로젝트 설정
└── PLAN.md                  # 이 문서
```

---

## 개선 히스토리

### 1단계: 기본 AlignedFreeSpacePacker 구현
- 정렬 점수 기반 그리디 알고리즘
- FreeSpace 관리

### 2단계: 유전 알고리즘 추가
- GeneticAlignedFreeSpacePacker
- 진화 기반 최적화

### 3단계: 백트래킹 전략
- BeamSearchPacker
- beam_width로 탐색 범위 제어

### 4단계: 그룹화 휴리스틱
- LookAheadPacker
- 같은 크기 조각들 함께 배치

### 5단계: 그룹 보존 유전 알고리즘
- GeneticGroupPreservingPacker
- 작업 편의성 고려

### 6단계: 영역 기반 패킹 (초기)
- RegionBasedPacker 첫 구현
- 한 영역 = 한 그룹 (1:1 매핑)
- 문제: 일부 조각 배치 실패

### 7단계: 다중 그룹 영역 배치
- 한 영역 = N개 그룹 (1:N 매핑)
- tolerance 기반 호환 그룹 세트 생성
- 백트래킹으로 최적 조합 탐색

### 8단계: 2-Phase Cutting 알고리즘
- Phase 1: Trimming Cuts (차원 트리밍)
- Phase 2: Separation Cuts (조각 분리)
- 높이/너비별 sub-group화

### 9단계: 다중 판 배치 지원
- while 루프로 pack() 재구조화
- 남은 조각 자동 추적 및 다음 판 배치
- 무한 루프 방지 (최대 10장)

### 10단계: 프로젝트 단순화
- 전략 1~5 삭제
- RegionBasedPacker만 유지
- CLI 단순화 (전략 선택 UI 제거)
- 코드 라인 수 대폭 감소 (1115줄 삭제)

### 11단계: 길로틴 절단 통합 (2025-12-31)
- **FSM 재귀 방식 제거**: packing.py FSM은 유지하지만 region_based.py에서 호출 안 함
- **배치와 절단 통합**: `_pack_multi_group_region()`이 배치+절단 동시 수행
- **우선순위 시스템 구축**: priority 1-5 + region_index + sub_priority
- **길로틴 원칙 준수**: 영역 경계(priority 1)가 최우선 실행
- **자투리 영역 독립 처리**: 상단 자투리를 별도 scrap 영역으로 추가
- **영역별 묶음 처리**: region_index로 한 영역 완료 후 다음 영역
- **임계값 제거**: kerf보다 크면 무조건 trim (10mm 조건 삭제)
- **절단선 증가**: 11개 → 15개 (모든 조각 완전 분리 + 자투리 trim)

---

## 향후 개선 방향

### 단기 (구현 가능)
- [ ] 다단 배치 지원 (한 영역에 여러 행/열)
- [ ] 동적 tolerance 조정 (그룹별 최적 값)
- [ ] 3개 이상 그룹 조합 세트 생성

### 중기 (고려 중)
- [ ] 수직 영역 세트 지원 (현재는 수평만)
- [ ] 원판 크기 자동 최적화
- [ ] CSV/JSON 입력 지원

### 장기 (연구 필요)
- [ ] 비정형 조각 지원
- [ ] 우선순위 기반 조각 배치
- [ ] 실시간 시각화

---

## 알려진 제한사항

### 회전 불허 시 배치율
- 회전을 허용하지 않으면 일부 조각이 다음 판으로 넘어갈 수 있음
- 예시: 369×640 조각이 높이가 커서 독립 판 필요
- 해결: 다중 판 배치 지원으로 모든 조각 100% 배치 보장

### Tolerance 값
- 현재 고정값 100mm
- 조각 크기에 따라 조정 필요할 수 있음
- 향후: 동적 조정 알고리즘 필요

### 공간 활용률
- Guillotine Cut 제약으로 인해 이론적 최적값보다 낮을 수 있음
- 회전 허용 시: ~66%
- 회전 불허 시: ~50%

---

## 사용 방법

### CLI 실행

```bash
# 기본 실행
uv run woodcut

# 빌드 후 실행
uv build
woodcut
```

### 입력 파라미터

프로그램 실행 시 대화형으로 입력:

1. **원판 너비** (mm, 기본값 2440)
2. **원판 높이** (mm, 기본값 1220)
3. **톱날 두께 (kerf)** (mm, 기본값 5)
4. **조각 회전 허용 여부** (y/n, 기본값 y)

### 출력 결과

**콘솔 출력:**
- 배치 결과 요약 (판 수, 조각 수, 사용률)
- 절단 순서 (번호, 방향, 위치)
- 조각 크기 검증 결과 (정확도 확인)

**PNG 파일:**
- 파일명: `cutting_plan_region_based_<timestamp>.png`
- 위치: `output/` 디렉토리
- 내용: 배치도, 절단선, 조각 색상 구분

---

## 디버깅 가이드

### 절단선 문제

**증상:** 절단선이 조각을 잘못 자르거나 Guillotine 제약 위반

**확인 사항:**
1. 배치 결과 확인 (조각들이 Guillotine 가능한 패턴인가?)
2. `_generate_trimming_cuts` 로직 확인 (서브그룹화 제대로 동작하는가?)
3. `_split_region` 로직 확인 (우선순위 정렬, placed_w/h 업데이트)
4. 영역 경계 출력으로 재귀 추적

**DEBUG 코드 추가 예시:**
```python
# packing.py의 _generate_trimming_cuts() 메서드
print(f"[TRIM-H] y={y_start}, req_h={req_h}, cut_y={cut_y}, " +
      f"region=({region.y}, {region.y + region.height}), " +
      f"pieces={len(pieces_with_height)}")
```

### 조각 크기 부정확

**증상:** 일부 조각이 필요한 크기와 다르게 절단됨

**확인 사항:**
1. `placed_w/h` 업데이트 확인 (트리밍 절단 시 설정되는가?)
2. 후처리 단계 확인 (미설정 조각 처리)
3. `_all_pieces_exact` 검증 로직 확인

**DEBUG 코드 추가 예시:**
```python
# packing.py의 _split_region() 메서드
for piece in pieces_crossing:
    print(f"[TRIM] Piece at ({piece['x']},{piece['y']}) " +
          f"trimmed to placed_h={piece.get('placed_h', 'UNSET')}")
```

### 배치 실패

**증상:** 일부 조각이 배치되지 않음

**확인 사항:**
1. tolerance 값 확인 (너무 작으면 호환 세트 생성 안 됨)
2. 백트래킹 로그 확인 (어느 단계에서 실패하는가?)
3. 다중 판 지원 확인 (remaining_pieces 추적)

**해결 방법:**
- tolerance 값 증가 (기본 100mm → 150mm)
- 단일 그룹 세트 폴백 확인
- 판 수 제한 확인 (현재 최대 10장)

### 성능 문제

**증상:** 실행 시간이 너무 오래 걸림

**확인 사항:**
1. 조각 개수 확인 (50개 이상이면 느릴 수 있음)
2. 백트래킹 깊이 확인
3. 호환 세트 개수 확인 (너무 많으면 탐색 시간 증가)

**해결 방법:**
- 조각 개수 줄이기 (그룹화로 이미 최적화됨)
- tolerance 값 조정으로 세트 개수 조절
- 백트래킹 최대 깊이 제한 추가 (향후)

---

## 기술 스택

### 언어 및 런타임
- **Python 3.10+** (match-case 문법 사용)
- 최신 문법 적극 활용 (타입 힌트, match-case, walrus 연산자 등)

### 의존성
- **matplotlib**: 배치도 시각화
- **uv**: 패키지 관리 및 빌드 도구

### 코딩 스타일
```python
# 타입 힌트 사용 (PEP 484, 585, 604)
def pack(self, pieces: list[tuple[int, int, int]]) -> list[dict]:
    ...

# match-case 사용 (Python 3.10+)
match cut['type']:
    case 'horizontal':
        ...
    case 'vertical':
        ...

# walrus 연산자 사용
if (req_h := piece.get('height')) > max_height:
    ...
```

---

## 참고 자료

### Guillotine Cut 알고리즘
- 2D Bin Packing Problem
- Guillotine Constraint
- Recursive Partitioning

### 관련 논문/자료
- Maximal Rectangles Algorithm
- Skyline Algorithm
- Best-Fit Decreasing Height (BFDH)

### 프로젝트 의존성
- Python 3.10+
- matplotlib (시각화)
- uv (패키지 관리)

---

## 버전 히스토리

### v0.1.0 (2025-12-27)
- RegionBasedPacker 구현 완료
- 다중 그룹 영역 배치 지원
- 2-Phase Cutting 알고리즘
- 다중 판 배치 지원
- 전략 1~5 삭제 및 프로젝트 단순화
- CLI 사용성 개선
