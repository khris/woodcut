# Woodcut 기술 스택

## 언어 및 버전
- **Python**: 3.10+ (최신 문법 사용)
- **패키지 매니저**: uv

## 빌드 시스템
- **빌드 백엔드**: uv_build
- **설정 파일**: pyproject.toml

## 핵심 의존성
- **matplotlib**: >=3.7.0 (시각화)
- **fastapi**: >=0.115.0 (웹 API)
- **uvicorn**: >=0.32.0 (ASGI 서버)

## 개발 도구
- **ruff**: >=0.14.10 (린팅/포맷팅)

## 진입점
- CLI 명령어: `woodcut` → `woodcut.cli:main`
