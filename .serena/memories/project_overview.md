# Woodcut 프로젝트 개요

## 목적
목재/MDF 원판에서 필요한 조각들을 **Guillotine Cut 제약** 하에 최소 판으로 재단하는 최적화 도구

## 핵심 제약사항
- **Guillotine Cut만 가능**: 영역 전체를 관통하는 일직선 절단만 허용
- **톱날 두께(kerf)**: 5mm 고려
- **회전**: 사용자 선택 가능
- **테두리 손실**: 각 변 5mm

## 주요 기능
1. 대화형 CLI - 조각 입력 및 재단 계획
2. 웹 인터페이스 - FastAPI 기반
3. 시각화 - matplotlib로 재단 계획 표시
4. 다중 전략:
   - 정렬 우선 자유 공간 (빠름, 안정적)
   - 하이브리드 (높이 그룹 + 자유 공간)
   - 유전 알고리즘 (추천, 최적 탐색)
   - RegionBasedPacker (다중 그룹 영역 배치)

## 핵심 알고리즘
- **RegionBasedPacker**: 다중 그룹 영역 배치 (1:N 매핑), 백트래킹 최적화
- **2-Phase Cutting**:
  - Phase 1: Trimming Cuts (조각을 정확한 크기로)
  - Phase 2: Separation Cuts (조각 분리)
- **서브그룹화**: 같은 위치, 다른 높이/너비 조각 독립 처리
