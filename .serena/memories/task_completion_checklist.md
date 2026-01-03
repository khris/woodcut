# 작업 완료 시 체크리스트

## 코드 변경 후 필수 작업

### 1. 코드 검증
```bash
# 문법 체크
python -m py_compile src/woodcut/*.py

# 린팅
ruff check .
```

### 2. 테스트 실행
```bash
# 기본 테스트 (회전 허용)
echo -e "2440\n1220\n5\ny" | uv run woodcut

# 회전 불허 테스트
echo -e "2440\n1220\n5\nn" | uv run woodcut
```

### 3. 결과 확인
- [ ] 모든 조각이 배치되었는가?
- [ ] 조각 크기가 정확한가? (±1mm 오차 허용)
- [ ] Guillotine 제약을 준수하는가?
- [ ] 시각화 이미지가 올바른가? (output/ 디렉토리 확인)
- [ ] 에러 메시지가 없는가?

### 4. IntelliJ MCP 사용 시
```
# 파일 문제 확인
mcp__jetbrains__get_file_problems(파일경로)

# 포맷팅 적용
mcp__jetbrains__reformat_file(파일경로)
```

### 5. 문서 업데이트 (해당 시)
- [ ] PLAN.md 업데이트 (알고리즘 변경 시)
- [ ] AGENTS.md 업데이트 (가이드라인 변경 시)
- [ ] README.md 업데이트 (사용법 변경 시)

### 6. Git 커밋 (작업 완료 시)
```bash
git status
git add .
git commit -m "타입: 변경 내용 설명"
```

## 버그 수정 시 추가 체크
- [ ] 재현 테스트 케이스 작성
- [ ] 근본 원인 파악 및 해결
- [ ] 회귀 테스트 통과 (기존 기능 동작 확인)

## 새 기능 추가 시 추가 체크
- [ ] 기존 알고리즘 동작 유지 확인
- [ ] 새 기능은 옵션으로 제공
- [ ] 사용 예시 포함한 문서 작성

## 알고리즘 수정 시 특별 주의
- [ ] Guillotine 제약 위반 없는지 확인
- [ ] placed_w/h 업데이트 확인 (트리밍 시)
- [ ] 서브그룹화 로직 확인 (다양한 높이 처리)
- [ ] 절단선 우선순위 확인 (trimming > separation)
