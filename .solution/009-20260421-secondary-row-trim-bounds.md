# secondary_row_trim 컷이 인접 컬럼을 가로지르는 버그 — 수정

- **작성일**: 2026-04-21
- **작성자**: Hong Segi + Claude
- **상태**: 승인됨
- **관련 스펙**: [007-fallback-trim-accuracy](007-20260421-fallback-trim-accuracy.md) (검증 중 발견)

## 1. 배경

007 검증 중 Sheet 1 시각화에서 H 컷이 100×764 조각을 물리적으로 가로지르는 것이 확인됨.

```
# 3 H pos= 565 start=   0 end=2440 type=secondary_row_trim
# 4 H pos= 850 start=   0 end=2440 type=secondary_row_trim
```

region 너비 전체(2440)까지 확장되는데, 해당 region 내 stacked 컬럼(2000×280, x=0~2000) 오른쪽에는 intact 100×764 조각이 y=0~764 범위로 존재. y=565 H컷이 그 조각을 물리적으로 바이섹트 → **Guillotine 위반**.

또 동일 위치(y=565)에 `stacked_separation`(start=0, end=2000) 컷이 별도로 emitted되어 **중복**.

## 2. 원인

[region_based.py:935](../src/woodcut/strategies/region_based.py:935) — secondary_row_trim 생성 시 `end = region['x'] + region['width']`. 그룹의 실제 오른쪽 경계 `x_end`(`secondary_rows` dict에 이미 담겨 있음)가 아닌 region 전체 너비를 사용.

## 3. 수정

`end = x_end`로 변경. 컷이 생성된 그룹 자신의 수평 범위로만 한정.

- Stacked 컬럼 단일 조각 그룹(x=0, w=2000)의 경우 `x_end = 2000` → 올바른 컷.
- 동일 위치의 `stacked_separation`과 start/end가 정확히 일치 → 시각적 중복이지만 동일 컷 한 번만 실행하면 되므로 cosmetic.

## 4. 검증 계획

- 재현 케이스 Sheet 1 cut list: `#3`, `#4`의 `end`가 2000이 되는지.
- 시각화: 100×764 조각을 가로지르는 H 선 없는지.
- 기존 회귀: baseline 11 / hyuptag 동일 결과 유지.

## 5. 구현 순서

- [ ] 9-1. `end` 필드 `x_end` 로 교체.
- [ ] 9-2. 재현 케이스 cut list 검증.
- [ ] 9-3. 시각화 확인.
- [ ] 9-4. 회귀 확인 (baseline 11, hyuptag).
- [ ] 9-5. 커밋.
