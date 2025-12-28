# Woodcut

목재 원판에서 필요한 조각들을 Guillotine Cut 제약 하에 최소 판으로 재단하는 최적화 도구입니다.

## 설치

```bash
# 의존성 설치
uv sync

# 또는 직접 설치
uv pip install -e .
```

## 사용법

```bash
# CLI 실행
uv run woodcut

# 빌드된 패키지 실행
woodcut
```

전략 선택:
1. 정렬 우선 자유 공간 (빠름, 안정적)
2. 하이브리드 (높이 그룹 + 자유 공간)
3. 유전 알고리즘 (추천, 최적 탐색)

## 개발

```bash
# 의존성 동기화
uv sync

# 패키지 빌드
uv build

# 빌드 결과 확인
ls dist/
```

## 프로젝트 구조

```
woodcut/
├── src/
│   └── woodcut/
│       └── __init__.py      # 메인 알고리즘 및 CLI
├── pyproject.toml           # 프로젝트 설정 (uv_build 사용)
├── AGENTS.md                # 알고리즘 상세 문서
└── README.md                # 이 파일
```

## 핵심 제약사항

- **Guillotine Cut만 가능**: 일직선 절단, 중간에 멈출 수 없음
- **톱날 두께(kerf)**: 5mm
- **회전 가능**: 단, 결이 없는 목재를 사용할 때는 불가능으로 변경 가능
- **테두리 손실**: 각 변 5mm

## 자세한 내용

알고리즘 및 아키텍처 상세 내용은 [AGENTS.md](AGENTS.md)를 참고하세요.
