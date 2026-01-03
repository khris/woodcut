# Woodcut 코드 스타일 및 컨벤션

## Python 스타일

### 1. 최신 문법 우선 (Python 3.10+)
```python
# ✅ match-case 사용
match cut['type']:
    case 'horizontal':
        process_horizontal(cut)
    case 'vertical':
        process_vertical(cut)

# ✅ 타입 힌트 적극 활용
def pack(self, pieces: list[tuple[int, int, int]]) -> list[dict]:
    ...

# ✅ walrus 연산자
if (req_h := piece.get('height')) > max_height:
    ...
```

### 2. 네이밍
- 변수/함수: snake_case
- 클래스: PascalCase
- 상수: UPPER_SNAKE_CASE

### 3. 주석 및 문서
- **언어**: 한국어 (주석, docstring, 문서 모두)
- **주석 철학**: "왜(why)" 설명, "무엇(what)"은 코드로 표현
- **Docstring**: 함수/메서드에 필수, Google 스타일

### 4. 코드 구조
- 단순함 유지: 복잡한 추상화보다 명확한 로직
- 함수는 한 가지 일만 수행
- 알고리즘 정확성 > 성능 최적화

### 5. 파일 인코딩
- UTF-8

## Git 커밋 메시지
```
feat: 새 기능 추가
fix: 버그 수정
docs: 문서 업데이트
refactor: 리팩토링
test: 테스트 추가/수정
```

## 핵심 원칙
1. ✅ Guillotine 제약 절대 준수
2. ✅ 모든 조각 정확한 크기로 절단
3. ✅ Python 3.10+ 최신 문법 사용
4. ✅ 테스트로 정확성 검증
5. ✅ 문서 업데이트 필수
