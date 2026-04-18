"""영역 기반 패킹 전략 + 그룹 자동 분할

RegionBasedPacker의 Fallback 전략:
- 배치 실패 시 큰 그룹을 자동 분할하여 재시도
- 무한 루프 방지: 분할 후에도 실패하면 즉시 중단
"""

from __future__ import annotations
from .region_based import RegionBasedPacker


class RegionBasedPackerWithSplit(RegionBasedPacker):
    """그룹 자동 분할을 지원하는 영역 기반 패커

    RegionBasedPacker를 상속하여 다음 기능 추가:
    - 실패 후 분할: 회전 옵션 먼저 시도, 실패 시에만 그룹 분할
    - 무한 루프 방지: 분할 후에도 배치 실패 시 즉시 중단

    부모의 multi-stock pack() 오케스트레이션을 그대로 상속하고,
    _pack_single_plate()만 오버라이드하여 분할 재시도 로직을 삽입.
    """

    def _pack_single_plate(self, remaining_pieces: list[dict]) -> dict:
        """원판 1장 패킹 (그룹 분할 폴백 포함).

        1차 시도: 정규 백트래킹
        2차 시도: 실패 시 큰 그룹 분할 후 재시도

        부모의 `FreeSpace` 기반 단순 폴백은 사용하지 않음 —
        분할 재시도 실패 시 빈 pieces의 plate를 반환하여
        부모 pack()이 stock 소진/중단 판단하게 한다.

        Returns:
            plate dict: {'width', 'height', 'pieces', 'cuts', 'free_spaces'}
        """
        print("\n=== 원판: 다중 그룹 영역 배치 시작 (분할 지원) ===")
        print(f"남은 조각: {len(remaining_pieces)}개")

        groups = self._group_by_exact_size(remaining_pieces)

        print(f"\n레벨 1: {len(groups)}개 그룹 생성")
        for i, group in enumerate(groups):
            print(f"  그룹 {i+1}: {group['size'][0]}×{group['size'][1]}mm, {group['count']}개 조각, 총 면적 {group['total_area']:,}mm²")

        # 1차 시도: 분할 없이 백트래킹
        plate = self._try_pack_groups(groups)
        if plate['pieces']:
            self._print_plate_summary(plate)
            return plate

        # 2차 시도: 그룹 분할 후 재시도
        print("\n⚠️  배치 실패, 큰 그룹 분할 후 재시도...")
        groups = self._split_oversized_groups(groups)
        print(f"분할 후 그룹 수: {len(groups)}개")

        plate = self._try_pack_groups(groups)
        if plate['pieces']:
            self._print_plate_summary(plate)
            return plate

        # 분할 후에도 실패 — 빈 plate 반환
        print("\n❌ 오류: 원판에 조각을 배치할 수 없습니다")
        print(f"남은 조각: {len(remaining_pieces)}개")
        for idx, piece in enumerate(remaining_pieces[:3]):
            print(f"  {idx+1}. {piece['width']}×{piece['height']}mm")
        if len(remaining_pieces) > 3:
            print(f"  ... 외 {len(remaining_pieces) - 3}개")
        return plate

    def _try_pack_groups(self, groups: list[dict]) -> dict:
        """그룹 리스트로부터 plate 1장 구성 시도.

        백트래킹 실패 시 pieces가 비어 있는 plate dict 반환 —
        호출 측에서 `not plate['pieces']`로 실패 판정.

        Returns:
            plate dict: {'width', 'height', 'pieces', 'cuts', 'free_spaces'}
        """
        group_options = self._generate_group_options(groups)
        all_variants = self._flatten_group_options(group_options)
        regions = self._allocate_anchor_backtrack(all_variants)

        if not regions:
            print("\n⚠️  백트래킹 실패")
            return {
                'width': self.plate_width,
                'height': self.plate_height,
                'pieces': [],
                'cuts': [],
                'free_spaces': [],
            }

        self._optimize_trim_placement(regions)
        return self._build_plate_from_regions(regions)

    def _print_plate_summary(self, plate: dict) -> None:
        """배치 완료 로그 + 크기별 배치 개수 검증 출력."""
        print("\n=== 원판: 다중 그룹 영역 배치 완료 ===")
        print(f"  배치된 조각: {len(plate['pieces'])}개")
        print(f"  절단선: {len(plate['cuts'])}개\n")

        placed_sizes_count: dict[tuple[int, int], int] = {}
        for p in plate['pieces']:
            size_key = (p['width'], p['height'])
            placed_sizes_count[size_key] = placed_sizes_count.get(size_key, 0) + 1

        print("\n=== 배치 검증 ===")
        for size_key, count in placed_sizes_count.items():
            print(f"  {size_key[0]}×{size_key[1]}: {count}개 배치")

    def _split_oversized_groups(self, groups: list[dict]) -> list[dict]:
        """한 행에 들어가지 않는 그룹을 자동 분할.

        각 분할 조각은 원본 pieces 리스트의 슬라이스 참조를 공유 —
        조각 총 개수는 보존된다.

        Args:
            groups: 그룹 리스트

        Returns:
            분할된 그룹 리스트 (원본 그룹 순서 유지, 분할분은 순차 삽입)
        """
        result = []

        for group in groups:
            w, h = group['size']
            count = group['count']
            pieces = group['pieces']

            # 수평 배치 (비회전): w×h 그대로
            max_horizontal = (self.plate_width + self.kerf) // (w + self.kerf) if h <= self.plate_height else 0

            # 수평 배치 (회전): h×w 로 회전, 회전 허용 시
            max_rotated = (self.plate_width + self.kerf) // (h + self.kerf) if self.allow_rotation and w <= self.plate_height else 0

            # 회전 vs 비회전 중 더 많이 들어가는 쪽
            if max_rotated > max_horizontal:
                max_count = max_rotated
                best_option = 'rotated'
            else:
                max_count = max_horizontal
                best_option = 'horizontal'

            if max_count == 0:
                print(f"  ⚠️  {w}×{h}mm 조각이 원판보다 큽니다")
                result.append(group)
                continue

            if count <= max_count:
                result.append(group)
            else:
                option_desc = f"회전 {max_count}개" if best_option == 'rotated' else f"{max_count}개"
                print(f"  분할: {w}×{h}mm {count}개 → {option_desc}씩 그룹")

                remaining_count = count
                piece_idx = 0

                while remaining_count > 0:
                    split_count = min(max_count, remaining_count)

                    result.append({
                        'size': (w, h),
                        'count': split_count,
                        'pieces': pieces[piece_idx:piece_idx + split_count],
                        'total_area': w * h * split_count
                    })

                    remaining_count -= split_count
                    piece_idx += split_count

        return result
