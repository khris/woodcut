# Woodcut 추천 명령어

## 개발 환경 설정
```bash
# 의존성 설치/동기화
uv sync

# Python 버전 확인
python --version  # 3.10 이상이어야 함
```

## 실행
```bash
# CLI 대화형 모드 (기본)
uv run woodcut

# 웹 서버 시작
uv run woodcut web

# 빌드된 패키지 실행 (설치 후)
woodcut
woodcut web
```

## 빌드
```bash
# 패키지 빌드
uv build

# 빌드 결과 확인
ls dist/
```

## 개발 도구
```bash
# 코드 린팅
ruff check .

# 코드 포맷팅 (추정)
ruff format .
```

## 테스트
```bash
# 회전 허용 테스트
echo -e "2440\n1220\n5\ny" | uv run woodcut

# 회전 불허 테스트
echo -e "2440\n1220\n5\nn" | uv run woodcut
```

## Git 작업
```bash
# 상태 확인
git status

# 커밋
git add .
git commit -m "feat: 새 기능 설명"

# 푸시
git push origin main
```

## 시스템 명령 (macOS)
```bash
# 디렉토리 목록
ls -la

# 파일 찾기
find . -name "*.py"

# 텍스트 검색
grep -r "pattern" .

# 트리 구조 (tree 설치 필요)
tree src/
```

## IDE/MCP 사용 시 주의
IntelliJ IDEA가 연결된 경우 다음 작업은 JetBrains MCP 도구 사용:
- 파일 읽기: `mcp__jetbrains__get_file_text_by_path`
- 파일 검색: `mcp__jetbrains__find_files_by_name_keyword`
- 텍스트 검색: `mcp__jetbrains__search_in_files_by_text`
- 리팩토링: `mcp__jetbrains__rename_refactoring`

쉘 명령(`cat`, `grep`, `find` 등) 대신 MCP 도구 우선 사용!
