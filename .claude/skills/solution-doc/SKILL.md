---
name: solution-doc
description: woodcut 프로젝트의 .solution/ 디렉터리에 디자인·구현 플랜 문서를 남기는 컨벤션. 새 기능·비자명 버그 수정·아키텍처 변경·알고리즘 수정 등 구현 플랜을 세울 때마다 호출. /plan 슬래시 모드, feature-dev 서브에이전트, ExitPlanMode 등 플래닝 워크플로우를 사용하는 경우 병행 실행 필수.
---

# .solution 플랜 문서 작성 규약

woodcut 프로젝트는 **모든 비자명 플랜을 `.solution/`에 문서로 남기는** 컨벤션을 따른다. `~/.claude/plans/*.md` 임시 플랜은 approval 직후 휘발되지만, `.solution/*.md`는 커밋되어 영구 기록으로 남는다.

## 언제 작성하는가

**반드시 작성** (신규 `.solution/NNN-....md` 파일 생성):

- 새 기능 추가 (CLI 옵션, API 필드, 전략 등)
- 알고리즘 수정 (region_based 로직, guillotine cut, stock 선택 등)
- 비자명 버그 수정 (콜 사이트 여러 곳을 만지거나 동작 의미가 바뀌는 경우)
- 아키텍처·데이터 구조 변경 (pack() 반환형, plate dict 스키마 등)
- 검증 체크리스트·코딩 컨벤션 같은 프로세스 결정

**작성 불필요**:

- 오타·공백·한두 줄 수정
- 단순 리팩토링 (동작 불변, 공개 API 영향 없음)
- README/주석만 업데이트

## 네이밍 규약

```
.solution/NNN-YYYYMMDD-slug.md          # 디자인 + 플랜 통합 (짧은 작업)
.solution/NNN-YYYYMMDD-slug.md          # 디자인 스펙 (규모 있는 작업)
.solution/NNN-YYYYMMDD-slug-plan.md     # 구현 플랜 (규모 있는 작업, 스펙과 쌍)
```

- `NNN`: 3자리 연번. 기존 최댓값 + 1. `ls .solution/ | sort`로 확인.
- `YYYYMMDD`: 작성일 (ISO 기본). 메모리의 `currentDate` 또는 `date +%Y%m%d` 사용.
- `slug`: kebab-case 한두 단어 영문 키워드 (예: `multi-size-stocks`, `stock-shortage-reporting`).

## 필수 섹션

다음 구조를 따른다 (기존 문서 참조: `004-20260418-multi-size-stocks.md`, `003-20260110-verification-checklist.md`):

```markdown
# 제목 — 디자인 + 구현 플랜

- **작성일**: YYYY-MM-DD
- **작성자**: 사용자 이름 + Claude
- **상태**: 승인됨 / 검토중 / 폐기
- **관련 스펙**: (있다면 다른 .solution 파일 링크)

## 1. 배경과 목표
왜 이 변경이 필요한가 (문제, 트리거, 기대 결과)

## 2. 설계 결정
핵심 의사결정과 근거. 대안 비교는 최소화하고 채택한 설계만 명확히.

## 3. 변경 대상
| 파일 | 변경 |
|---|---|
| ... | ... |

## 4. 재사용
기존 유틸·패턴 활용 명시 (AGENTS.md "단순함 유지" 원칙)

## 5. 검증 계획
AGENTS.md의 5단계 체크리스트 적용:
- 수치 검증
- 시각적 검증 (시각화 또는 자동화된 스모크)
- 회귀 테스트
- 제약 조건 (guillotine, kerf, ±1mm)
- 엣지 케이스

## 6. 알려진 한계 (선택)
트레이드오프, 스코프 밖 항목

## 7. 구현 순서
체크박스 또는 번호 목록. agentic execution 시 task-by-task 추적 가능하게.
```

## 워크플로우 통합

1. **Plan Mode / `/plan` 진입 시**: 기존 플로우대로 `~/.claude/plans/<session>.md`에 드래프트 작성.
2. **ExitPlanMode 호출 직전 OR 직후**: 승인된 플랜을 `.solution/NNN-YYYYMMDD-slug.md`로 복사·정돈해 **반드시 저장**.
3. **구현 시작 시**: 커밋에 `.solution/` 문서를 함께 포함하거나 첫 구현 커밋 직전에 별도 커밋으로 선반영.
4. **리뷰·회고 시**: 실제 구현과 다른 점이 있으면 `.solution/` 문서에 짧은 "실제 구현 차이" 섹션 추가.

## 체크리스트

플랜 문서를 커밋하기 전:

- [ ] 파일명이 `NNN-YYYYMMDD-slug.md` 패턴인가 (NNN은 기존 최댓값 +1)
- [ ] 배경/설계/변경대상/검증 4개 섹션 포함
- [ ] 검증 계획이 AGENTS.md 5단계와 매핑되는가
- [ ] 상태 필드가 명시되어 있는가 (대부분 "승인됨")
- [ ] 관련 선행 스펙이 있다면 링크됨

## 안티패턴

- ❌ `.solution/` 대신 PR 설명·커밋 메시지로만 설계 설명 → 휘발됨
- ❌ 구현 완료 후에야 문서 작성 → 사후 합리화 위험
- ❌ 번호 건너뛰기·중복 → 시계열 추적 어려워짐
- ❌ 한국어/영어 혼용 무질서 → 본문은 한국어, 식별자·파일명·코드는 원형 유지 (AGENTS.md 규약)
