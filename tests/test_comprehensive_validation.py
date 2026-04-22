"""현 상태 광범위 검증 — 조각 무결성·Guillotine·중복·겹침 점검.

실행:
    uv run python tests/test_comprehensive_validation.py

검증 항목:
1) placed_w/h 원본 크기 일치 (±1mm)
2) 조각 간 물리적 겹침 없음
3) cut의 start/end가 plate 범위 안
4) cut 중복 (direction/position/start/end 완전 동일) 없음
5) Guillotine 순서 — 각 cut이 "자기보다 앞 order의 모든 cut으로 만들어진 서브영역" 중 하나 안에 전체 관통
6) cut의 '자기 서브영역'이 실제 빈 직사각형 (조각 안 가로지름)
7) unplaced 수량 = 입력 - 배치된 수량
"""
from __future__ import annotations

import sys
import traceback
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))

import matplotlib
matplotlib.use('Agg')

from woodcut.strategies.region_based import RegionBasedPacker


# ---------------- helpers ----------------

def piece_rect(p: dict) -> tuple[int, int, int, int]:
    """(x, y, w, h) — placed 좌표계."""
    return p['x'], p['y'], p['placed_w'], p['placed_h']


def rects_overlap(a, b, tol=0) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    if ax + aw <= bx + tol or bx + bw <= ax + tol:
        return False
    if ay + ah <= by + tol or by + bh <= ay + tol:
        return False
    return True


def validate_placed_sizes(pieces: list[dict], kerf: int, errors: list[str], ctx: str):
    for i, p in enumerate(pieces):
        w0, h0 = p['width'], p['height']
        pw, ph = p['placed_w'], p['placed_h']
        rotated = p.get('rotated', False)
        exp_w, exp_h = (h0, w0) if rotated else (w0, h0)
        if abs(pw - exp_w) > 1 or abs(ph - exp_h) > 1:
            errors.append(
                f"{ctx} piece[{i}] placed={pw}x{ph} but expected {exp_w}x{exp_h} "
                f"(orig {w0}x{h0}, rot={rotated})"
            )


def validate_no_overlap(pieces: list[dict], errors: list[str], ctx: str):
    for i in range(len(pieces)):
        for j in range(i + 1, len(pieces)):
            if rects_overlap(piece_rect(pieces[i]), piece_rect(pieces[j])):
                errors.append(
                    f"{ctx} overlap: piece[{i}] {piece_rect(pieces[i])} vs piece[{j}] {piece_rect(pieces[j])}"
                )


def validate_bounds(pieces: list[dict], pw: int, ph: int, errors: list[str], ctx: str):
    for i, p in enumerate(pieces):
        x, y, w, h = piece_rect(p)
        if x < 0 or y < 0 or x + w > pw + 1 or y + h > ph + 1:
            errors.append(f"{ctx} piece[{i}] out of plate bounds: ({x},{y},{w},{h}) plate={pw}x{ph}")


def validate_cuts_basic(cuts: list[dict], pw: int, ph: int, errors: list[str], ctx: str):
    for c in cuts:
        d, pos, s, e = c['direction'], c['position'], c['start'], c['end']
        if d == 'H':
            if pos < 0 or pos > ph:
                errors.append(f"{ctx} cut #{c['order']} H pos={pos} out of plate [0,{ph}]")
            if s < 0 or e > pw + 1 or s >= e:
                errors.append(f"{ctx} cut #{c['order']} H range [{s},{e}] bad (plate w={pw})")
        elif d == 'V':
            if pos < 0 or pos > pw:
                errors.append(f"{ctx} cut #{c['order']} V pos={pos} out of plate [0,{pw}]")
            if s < 0 or e > ph + 1 or s >= e:
                errors.append(f"{ctx} cut #{c['order']} V range [{s},{e}] bad (plate h={ph})")
        else:
            errors.append(f"{ctx} cut #{c['order']} unknown direction={d}")


def validate_no_duplicate_cuts(cuts: list[dict], errors: list[str], ctx: str):
    seen: dict[tuple, int] = {}
    for c in cuts:
        key = (c['direction'], c['position'], c['start'], c['end'])
        if key in seen:
            errors.append(f"{ctx} duplicate cut: #{seen[key]} and #{c['order']} both {key}")
        else:
            seen[key] = c['order']


def validate_cut_not_crossing_piece(cuts: list[dict], pieces: list[dict], errors: list[str], ctx: str):
    """컷이 조각의 내부(경계 제외)를 지나가면 Guillotine 위반."""
    for c in cuts:
        d, pos, s, e = c['direction'], c['position'], c['start'], c['end']
        for i, p in enumerate(pieces):
            x, y, w, h = piece_rect(p)
            if d == 'H':
                if y < pos < y + h:
                    if s < x + w and e > x:
                        if s < x + w - 1 and e > x + 1:
                            errors.append(
                                f"{ctx} cut #{c['order']} H y={pos} [{s},{e}] crosses piece[{i}] "
                                f"({x},{y},{w},{h})"
                            )
            else:
                if x < pos < x + w:
                    if s < y + h and e > y:
                        if s < y + h - 1 and e > y + 1:
                            errors.append(
                                f"{ctx} cut #{c['order']} V x={pos} [{s},{e}] crosses piece[{i}] "
                                f"({x},{y},{w},{h})"
                            )


def validate_guillotine_order(cuts: list[dict], pw: int, ph: int, errors: list[str], ctx: str, kerf: int = 5):
    """각 cut이 '이전 cut들로 만들어진 서브영역 중 하나'를 전체 관통하는지 확인.

    수치 모델 (kerf 인식):
    - 서브영역 리스트를 (x, y, w, h) 로 유지.
    - 매 cut 처리 시 cut이 어떤 서브영역을 전체 관통하는지 찾아 그 서브영역을
      둘로 분할한다. 톱날 두께(`kerf`)만큼의 공간은 양쪽 자식에 포함되지 않고
      사라진다 — 즉 인접 subregion은 `pos + kerf`부터 시작.
    - 관통하는 서브영역이 없으면 Guillotine 순서 위반.
    """
    subregions = [(0, 0, pw, ph)]
    ordered = sorted(cuts, key=lambda c: c['order'])
    for c in ordered:
        d, pos, s, e = c['direction'], c['position'], c['start'], c['end']
        matched_idx = -1
        for idx, (rx, ry, rw, rh) in enumerate(subregions):
            if d == 'H':
                if ry < pos < ry + rh and abs(s - rx) <= 1 and abs(e - (rx + rw)) <= 1:
                    matched_idx = idx
                    break
            else:
                if rx < pos < rx + rw and abs(s - ry) <= 1 and abs(e - (ry + rh)) <= 1:
                    matched_idx = idx
                    break
        if matched_idx < 0:
            errors.append(
                f"{ctx} cut #{c['order']} {d} pos={pos} [{s},{e}] does not fully span any existing subregion "
                f"(Guillotine order violation)"
            )
            continue
        rx, ry, rw, rh = subregions.pop(matched_idx)
        if d == 'H':
            top_h = pos - ry
            bot_y = pos + kerf
            bot_h = ry + rh - bot_y
            if top_h > 0:
                subregions.append((rx, ry, rw, top_h))
            if bot_h > 0:
                subregions.append((rx, bot_y, rw, bot_h))
        else:
            left_w = pos - rx
            right_x = pos + kerf
            right_w = rx + rw - right_x
            if left_w > 0:
                subregions.append((rx, ry, left_w, rh))
            if right_w > 0:
                subregions.append((right_x, ry, right_w, rh))


# ---------------- test runner ----------------

CASES = [
    # (name, stocks, pieces, allow_rotation)
    ("baseline_rot_off", [(2440, 1220, 5)],
     [(800, 310, 2), (644, 310, 3), (371, 270, 4), (369, 640, 2)], False),
    ("baseline_rot_on",  [(2440, 1220, 5)],
     [(800, 310, 2), (644, 310, 3), (371, 270, 4), (369, 640, 2)], True),
    ("hyuptag_rot_off",  [(2440, 1220, 5)],
     [(560, 350, 2), (446, 50, 2), (369, 50, 2), (550, 450, 1),
      (450, 100, 1), (450, 332, 2), (450, 278, 1)], False),
    ("hyuptag_rot_on",   [(2440, 1220, 5)],
     [(560, 350, 2), (446, 50, 2), (369, 50, 2), (550, 450, 1),
      (450, 100, 1), (450, 332, 2), (450, 278, 1)], True),
    ("repro_rot_off",    [(2440, 1220, 2)],
     [(2000, 280, 4), (760, 260, 14), (100, 764, 2)], False),
    ("repro_rot_on",     [(2440, 1220, 2)],
     [(2000, 280, 4), (760, 260, 14), (100, 764, 2)], True),
    # 단일 조각
    ("single_big_rot_off", [(2440, 1220, 1)], [(2000, 1000, 1)], False),
    # 모든 조각이 매우 작음
    ("many_small_rot_off", [(2440, 1220, 3)], [(100, 100, 50)], False),
    # 세로로 긴 조각 (회전 금지 시 여러 플레이트)
    ("tall_narrow_rot_off", [(2440, 1220, 3)], [(200, 1000, 8)], False),
    # 가로로 긴 조각
    ("wide_short_rot_off", [(2440, 1220, 2)], [(2000, 200, 10)], False),
    # 혼합 크기 (solution 004 스타일)
    ("mixed_rot_off", [(2440, 1220, 3)],
     [(800, 600, 2), (600, 400, 4), (400, 300, 6), (300, 200, 8)], False),
    # 조각이 플레이트 정확히 맞음
    ("exact_fit_rot_off", [(1000, 1000, 1)], [(1000, 1000, 1)], False),
    # 한 조각이 플레이트 초과 (unplaced)
    ("too_big_rot_off", [(500, 500, 1)], [(1000, 1000, 2)], False),
    # 008 케이스의 축약본
    ("big_count_rot_off", [(2440, 1220, 3)], [(400, 200, 30)], False),
]


def run_case(name: str, stocks, pieces_in, allow_rotation: bool, kerf: int = 5):
    report_lines: list[str] = [f"\n==== CASE: {name}  stocks={stocks} pieces={pieces_in} rot={allow_rotation} ===="]
    errors: list[str] = []
    try:
        packer = RegionBasedPacker(stocks, kerf=kerf, allow_rotation=allow_rotation)
        plates, unplaced = packer.pack(pieces_in)
    except Exception as e:
        errors.append(f"{name}: pack() raised {type(e).__name__}: {e}")
        traceback.print_exc()
        return report_lines, errors

    total_placed = sum(len(pl['pieces']) for pl in plates)
    total_required = sum(c for _, _, c in pieces_in)
    report_lines.append(f"  placed={total_placed}, unplaced={len(unplaced)}, plates={len(plates)}")

    if total_placed + len(unplaced) != total_required:
        errors.append(f"{name}: count mismatch placed({total_placed}) + unplaced({len(unplaced)}) != required({total_required})")

    # 크기별 placed 집계
    by_size: dict[tuple, int] = defaultdict(int)
    for pl in plates:
        for p in pl['pieces']:
            by_size[(p['width'], p['height'])] += 1
    report_lines.append(f"  by_size_placed={dict(by_size)}")

    for i, plate in enumerate(plates):
        pw = plate['width']
        ph = plate['height']
        ctx = f"{name}/Sheet{i+1}"
        validate_placed_sizes(plate['pieces'], kerf, errors, ctx)
        validate_bounds(plate['pieces'], pw, ph, errors, ctx)
        validate_no_overlap(plate['pieces'], errors, ctx)
        validate_cuts_basic(plate['cuts'], pw, ph, errors, ctx)
        validate_no_duplicate_cuts(plate['cuts'], errors, ctx)
        validate_cut_not_crossing_piece(plate['cuts'], plate['pieces'], errors, ctx)
        validate_guillotine_order(plate['cuts'], pw, ph, errors, ctx)
        report_lines.append(f"  {ctx}: {len(plate['pieces'])} pieces, {len(plate['cuts'])} cuts")

    return report_lines, errors


def main():
    all_report: list[str] = []
    all_errors: list[str] = []
    for name, stocks, pieces_in, rot in CASES:
        rep, errs = run_case(name, stocks, pieces_in, rot)
        all_report.extend(rep)
        all_errors.extend(errs)

    print('\n'.join(all_report))
    print("\n" + "=" * 70)
    if all_errors:
        print(f"FAIL — {len(all_errors)} error(s):")
        for e in all_errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("PASS — all validations clean")
        sys.exit(0)


if __name__ == '__main__':
    main()
