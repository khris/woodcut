# Claude Code 프로젝트 지침

## ⚠️ 중요: 응답 언어 (최우선 규칙)
- **모든 응답은 반드시 한국어로 작성**
- **컴팩트(/compact) 후에도 한국어 유지 필수**
- 코드 주석도 한국어 사용
- 문서화도 한국어로 작성
- 영어 사용 절대 금지
- **계획은 자체적으로 관리하지 않고 무조건**
  - PLAN.md (주 계획)
  - .plan 디렉토리 (상세계획 md 파일들)
- 가장 적절하고 추상도가 높은 도구를 고를 것
  - 최대한 Serena와 JetBrains 통합 MCP를 사용하고 불가능한 경우 기본 기능 사용

## 패키지 관리자

### Python
- **기본 패키지 매니저: uv**
- 패키지 설치: `uv add <package>`
- 스크립트 실행: `uv run <script>.py`
- pip 사용 금지 (uv로 통일)

### JavaScript/TypeScript 생태계
- **기본 패키지 매니저: pnpm**
- 패키지 설치: `pnpm add <package>`
- 개발 의존성: `pnpm add -D <package>`
- 스크립트 실행: `pnpm run <script>`
- npm, yarn 사용 금지 (pnpm으로 통일)

## Git 커밋 메시지
- **Conventional Commits 형식 준수**
- 형식: `<type>(<scope>): <subject>`
- 타입:
  - `feat`: 새로운 기능 추가
  - `fix`: 버그 수정
  - `docs`: 문서 변경
  - `style`: 코드 포맷팅, 세미콜론 누락 등 (기능 변경 없음)
  - `refactor`: 코드 리팩토링 (기능 변경 없음)
  - `perf`: 성능 개선
  - `test`: 테스트 추가 또는 수정
  - `chore`: 빌드, 패키지 매니저 설정 등
  - `ci`: CI 설정 변경
- 예시:
  - `feat(cutting): add genetic algorithm optimization`
  - `fix(guillotine): correct region splitting logic`
  - `docs: update AGENTS.md with usage examples`

## 프로젝트 규칙
- 새로운 의존성 추가 시 반드시 위 패키지 매니저 사용
- 문서는 마크다운(.md) 형식으로 작성
- 코드 변경 전 관련 파일 먼저 읽기
- 테스트를 위하여 생성한 소스코드나 리소스 파일들은 커밋하지 않기
