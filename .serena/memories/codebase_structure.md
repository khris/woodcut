# Woodcut 코드베이스 구조

## 디렉토리 구조
```
woodcut/
├── src/woodcut/               # 메인 소스 코드
│   ├── __init__.py           # (레거시 메인 알고리즘?)
│   ├── cli.py                # CLI 진입점 (서브커맨드 라우팅)
│   ├── interactive.py        # 대화형 모드
│   ├── web.py                # 웹 서버 진입점
│   ├── packing.py            # Guillotine Cut 알고리즘
│   ├── visualizer.py         # 시각화 (matplotlib)
│   ├── strategies/           # 패킹 전략들
│   │   ├── __init__.py
│   │   ├── region_based.py  # RegionBasedPacker (추천)
│   │   ├── aligned_free_space.py
│   │   ├── genetic_*.py     # 유전 알고리즘 변형들
│   │   ├── beam_search.py
│   │   └── lookahead.py
│   └── web_app/             # 웹 UI
│       ├── server.py        # FastAPI 서버
│       └── static/          # 정적 파일 (HTML, CSS, JS)
├── pyproject.toml           # 프로젝트 설정
├── README.md                # 사용자 가이드
├── AGENTS.md                # AI 에이전트 개발 가이드
├── PLAN.md                  # 상세 기술 문서
├── SOLUTION.md              # 솔루션 설명
└── output/                  # 출력 이미지 (시각화)
```

## 주요 파일 역할

### 진입점
- **cli.py**: 메인 진입점, 서브커맨드 분기 (기본/web)
- **interactive.py**: 대화형 CLI 로직
- **web.py**: FastAPI 웹 서버 실행

### 핵심 알고리즘
- **packing.py**: Guillotine Cut 생성 알고리즘 (2-Phase)
- **strategies/region_based.py**: RegionBasedPacker (추천 전략)
- **visualizer.py**: matplotlib 시각화

### 데이터 흐름
```
입력 (pieces) → 그룹화 → 호환 세트 생성 → 백트래킹 영역 할당 → 
영역 내 배치 → Guillotine Cut 생성 → 시각화 + 검증
```

## 핵심 데이터 구조

### 조각 (piece)
```python
{
    'width': int,      # 원본 너비
    'height': int,     # 원본 높이
    'x': int,          # 배치 x 좌표
    'y': int,          # 배치 y 좌표
    'rotated': bool,   # 회전 여부
    'placed_w': int,   # 실제 너비 (회전 후)
    'placed_h': int    # 실제 높이 (트림 후)
}
```

### 절단선 (cut)
```python
{
    'type': str,       # 'horizontal' or 'vertical'
    'position': int,   # 절단 위치 (y or x)
    'priority': int,   # 우선순위 (1000+ = trimming)
    'affects': int     # 영향받는 조각 수
}
```

### 영역 (region)
```python
{
    'x': int,          # 영역 시작 x
    'y': int,          # 영역 시작 y
    'width': int,      # 영역 너비
    'height': int,     # 영역 높이
    'pieces': list     # 포함된 조각들
}
```
