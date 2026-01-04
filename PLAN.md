# Woodcut - 목재 재단 최적화

## 프로젝트 개요

Guillotine Cut 제약 하에서 목재/MDF 원판에 조각들을 효율적으로 배치하고 절단 순서를 생성하는 최적화 도구

- **목표**: 최소 판 수로 모든 조각 배치, 실제 작업 가능한 절단 순서 생성
- **제약**: Guillotine Cut (영역 전체 관통 직선 절단), 톱날 두께 5mm, 회전 선택 가능
- **입출력**: 조각 목록 입력 → 배치도 + 절단 순서 + PNG 시각화

---

## 현재 구현

### RegionBasedPacker (유일한 전략)

**핵심 개념:**
- **다중 그룹 영역 배치**: 한 영역에 여러 그룹 배치
- **정확한 그룹화**: 정확히 같은 크기끼리 그룹화 후 회전 옵션 생성
- **백트래킹 최적화**: 모든 그룹을 배치할 수 있는 최적 영역 조합 탐색
- **통합 절단**: 배치와 동시에 절단선 생성, 우선순위로 길로틴 원칙 보장

**참조**: 상세 알고리즘은 [ALGORITHM.md](ALGORITHM.md) 참조

---

## Two-Tier Priority System

길로틴 절단 순서를 보장하는 핵심 메커니즘:

**Tier 1 (전역)**: 모든 영역 경계선
- Priority = region_index (1, 2, 3, ...)
- 모든 영역 boundary를 먼저 실행

**Tier 2 (영역별)**: 영역 내부 절단
- Priority = region_index × 100 + offset
- 각 영역별로 순차 처리 (영역0 완료 → 영역1 → ...)

**실행 순서**:
```
P1, P2, P3 (모든 boundaries)
→ P10, P20, P21 (영역0 내부)
→ P110, P120, P121 (영역1 내부)
```

**결과**: 영역 경계를 먼저 자른 후 내부를 처리하여 완벽한 길로틴 순서 보장

---

## 테스트 결과

### 테스트 케이스 (11개 조각)
- 800×310 (2개), 644×310 (3개), 371×270 (4개), 369×640 (2개)

### 회전 허용
- **원판**: 1장
- **배치율**: 11/11 (100%)
- **사용률**: 66.1%
- **절단**: 15회 (길로틴 순서 준수)

### 회전 불허
- **원판**: 2장
- **배치율**: 11/11 (100%)
- **사용률**: 50.2% (판1), 15.9% (판2)

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

### 입력
대화형으로 입력: 원판 너비/높이(mm), kerf(mm), 회전 허용(y/n)

### 출력
- 콘솔: 배치 요약, 절단 순서, 검증 결과
- PNG: `output/cutting_plan_region_based_<timestamp>.png`

---

## 프로젝트 구조

```
woodcut/
├── src/woodcut/
│   ├── cli.py              # CLI 진입점
│   ├── interactive.py      # 대화형 모드
│   ├── visualizer.py       # 시각화
│   └── strategies/
│       └── region_based.py # RegionBasedPacker
├── ALGORITHM.md            # 알고리즘 상세
├── AGENTS.md               # AI 개발 가이드
└── PLAN.md                 # 이 문서
```

---

## 주요 버전 히스토리

### v0.1.0 - RegionBasedPacker (2025-12-27)
- 다중 그룹 영역 배치 구현
- 다중 판 지원
- 전략 1~5 삭제, RegionBasedPacker만 유지

### v0.2.0 - 길로틴 절단 통합 (2025-12-31)
- 배치와 절단 통합 (FSM 제거)
- 우선순위 시스템으로 길로틴 원칙 준수
- 절단선 11개 → 15개 (완전 분리 + 자투리 trim)

### v0.3.0 - Two-Tier Priority (2026-01-04)
- 전역/지역 우선순위 분리
- 영역 경계 우선 실행으로 길로틴 위반 해결

---

## 향후 개선 (단기)

- [ ] 다단 배치 지원 - 옵션 기반, 보수적 (상세: [.solution/002](.solution/002-20260104-multi-tier-placement.md))
- [ ] CSV/JSON 입력 지원
- [ ] 웹 UI 개선

---

## 솔루션 문서

프로젝트의 주요 개선 작업들은 `.solution/` 디렉터리에 별도 문서화:

- [001: Guillotine 절단 통합](.solution/001-20251231-guillotine-cutting-integration.md) - 배치와 절단 통합, Two-Tier Priority 시스템
- [002: 다단 배치](.solution/002-20260104-multi-tier-placement.md) - 남은 공간 활용 (계획 단계)

---

## 기술 스택

- **Python 3.10+** (match-case, 타입 힌트, walrus 연산자)
- **matplotlib** (시각화)
- **uv** (패키지 관리)
