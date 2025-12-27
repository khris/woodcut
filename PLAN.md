# Woodcut - MDF 재단 최적화 프로젝트

## 프로젝트 개요

MDF(목재) 재단 최적화를 위한 Guillotine Cut 알고리즘 구현

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

### Guillotine Cut 알고리즘 (2-Phase Cutting)

**Phase 1: Trimming Cuts (차원 트리밍)**
- 조각들을 필요한 크기로 정확히 자르는 절단선
- 같은 y/x 시작점의 조각들을 높이/너비별로 sub-group화
- 각 sub-group마다 독립적인 절단선 생성

**Phase 2: Separation Cuts (조각 분리)**
- 이미 트림된 조각들을 개별적으로 분리하는 절단선
- 조각의 하단/우측 + kerf 위치에 절단선 생성

**절단선 우선순위:**
- Trimming cuts: `priority = 1000 + affected_pieces`
- Separation cuts: `priority = affected_pieces`
- 우선순위 높은 순으로 정렬하여 실행

**재귀적 영역 분할:**
- 각 절단 후 영역을 2개로 분할
- 각 영역에서 독립적으로 절단선 생성 (재귀)
- `placed_w`/`placed_h` 설정으로 이미 트림된 조각 표시

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

        # 5. 각 영역 내 배치
        for region in regions:
            placed = self._pack_multi_group_region(region)
            plate['pieces'].extend(placed)

        # 6. Guillotine 절단선 생성
        self.generate_guillotine_cuts(plate)

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

### 4. 2-Phase Cutting 알고리즘

**Phase 1: Trimming Cuts**
```python
# y 시작점별 그룹화 → 높이별 sub-group화
y_groups = {}
for piece in region.pieces:
    y_groups[piece['y']].append(piece)

for y_start, pieces_at_y in y_groups.items():
    # 높이별 sub-group 생성
    height_subgroups = {}
    for p in pieces_at_y:
        req_h = p['width'] if p.get('rotated') else p['height']
        height_subgroups[req_h].append(p)

    # 각 높이별로 독립적인 절단선 생성
    for req_h, pieces_with_height in height_subgroups.items():
        cut_y = y_start + req_h
        if region.y < cut_y < region.y + region.height:
            # 절단선 생성
            trimming_cuts.append({
                'type': 'horizontal',
                'position': cut_y,
                'priority': 1000 + len(pieces_with_height)
            })
```

**Phase 2: Separation Cuts**
```python
# 조각의 하단/우측 + kerf 위치에 분리선
for piece in region.pieces:
    req_h = piece['width'] if piece.get('rotated') else piece['height']
    cut_y = piece['y'] + req_h + kerf

    if cut_y < region.y + region.height:
        separation_cuts.append({
            'type': 'horizontal',
            'position': cut_y,
            'priority': 1  # 낮은 우선순위
        })
```

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
- **절단 횟수**: 14회
- **영역**: 3개
  - 영역 1: 640×369 (2개, 회전) + 270×371 (4개, 회전)
  - 영역 2: 644×310 (3개)
  - 영역 3: 800×310 (2개)

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
