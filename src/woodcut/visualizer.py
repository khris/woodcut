"""시각화 모듈"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import Rectangle as MPLRect
from matplotlib import font_manager
import platform


def setup_korean_font():
    """한글 폰트 설정"""
    system = platform.system()
    if system == 'Darwin':
        fonts = ['AppleGothic', 'AppleSDGothicNeo', 'Nanum Gothic']
    elif system == 'Windows':
        fonts = ['Malgun Gothic', 'NanumGothic', 'Gulim']
    else:
        fonts = ['NanumGothic', 'Noto Sans CJK KR', 'UnDotum']

    available_fonts = [f.name for f in font_manager.fontManager.ttflist]
    for font in fonts:
        if font in available_fonts:
            plt.rcParams['font.family'] = font
            print(f"폰트 설정: {font}")
            return
    print("⚠️  한글 폰트를 찾지 못했습니다.")


def visualize_solution(plates, pieces, plate_width, plate_height):
    """시각화 함수

    Args:
        plates: 패킹 결과 (각 원판의 조각 배치 및 절단선 정보)
        pieces: 원본 조각 리스트 [(width, height, count), ...]
        plate_width: 원판 너비 (mm)
        plate_height: 원판 높이 (mm)
    """
    # 색상
    piece_types = set(f"{w}x{h}" for w, h, _ in pieces)
    colors = {ptype: plt.cm.Set3(i / len(piece_types))
              for i, ptype in enumerate(sorted(piece_types))}

    # 시각화
    fig, axes = plt.subplots(1, len(plates), figsize=(10 * len(plates), 5))
    if len(plates) == 1:
        axes = [axes]

    for plot_idx, plate in enumerate(plates):
        ax = axes[plot_idx]

        print(f"\n{'='*60}")
        print(f"원판 {plot_idx + 1}")
        print(f"배치된 조각: {len(plate['pieces'])}개")
        print(f"절단 횟수: {len(plate['cuts'])}회\n")

        # 절단선 순서 출력
        print("절단 순서:")
        for cut in plate['cuts']:
            direction = "수평" if cut['direction'] == 'H' else "수직"
            print(f"  {cut['order']:2d}. {direction} {cut['position']:4.0f}mm "
                  f"(영역 {cut['region_x']:.0f},{cut['region_y']:.0f} "
                  f"{cut['region_w']:.0f}×{cut['region_h']:.0f})")

        # 조각들의 최종 크기 검증
        print("\n조각 크기 검증 (상세):")
        all_exact = True
        for i, piece in enumerate(plate['pieces']):
            required = f"{piece['width']}×{piece['height']}"

            # 회전 고려
            if piece.get('rotated', False):
                req_w, req_h = piece['height'], piece['width']
            else:
                req_w, req_h = piece['width'], piece['height']

            # placed_w/h가 없으면 아직 트리밍 안됨
            if 'placed_w' not in piece or 'placed_h' not in piece:
                actual = "트리밍 전"
                match = "✗"
                all_exact = False
            else:
                actual = f"{piece['placed_w']}×{piece['placed_h']}"
                match = "✓" if (abs(piece['placed_w'] - req_w) <= 1 and
                               abs(piece['placed_h'] - req_h) <= 1) else "✗"
                if match == "✗":
                    all_exact = False

            pos = f"({piece['x']:.0f},{piece['y']:.0f})"
            print(f"  [{i+1}] {match} 위치: {pos}, 필요: {required}, 실제: {actual}, 기대: {req_w}×{req_h}")

        if all_exact:
            print("\n  ✅ 모든 조각이 정확한 크기입니다")
        else:
            print("\n  ❌ 일부 조각이 부정확합니다")

        ax.add_patch(MPLRect((0, 0), plate_width, plate_height,
                             fill=False, edgecolor='black', linewidth=2))

        total_area = 0
        for piece in plate['pieces']:
            x, y = piece['x'], piece['y']
            # placed_w/h가 없으면 회전 고려한 크기 사용
            if 'placed_w' in piece and 'placed_h' in piece:
                w, h = piece['placed_w'], piece['placed_h']
            else:
                if piece.get('rotated', False):
                    w, h = piece['height'], piece['width']
                else:
                    w, h = piece['width'], piece['height']
            orig = piece['original']

            piece_type = f"{orig[0]}x{orig[1]}"
            color = colors[piece_type]

            rect_patch = MPLRect((x, y), w, h,
                                linewidth=1, edgecolor='black',
                                facecolor=color, alpha=0.7)
            ax.add_patch(rect_patch)

            cx, cy = x + w/2, y + h/2
            label = f"{w}×{h}"
            if piece['rotated']:
                label += "\n(회전)"
            ax.text(cx, cy, label, ha='center', va='center',
                   fontsize=8, fontweight='bold')

            total_area += w * h

        # 절단선 - 영역 내에서만
        for cut in plate['cuts']:
            if cut['direction'] == 'H':
                ax.plot([cut['start'], cut['end']],
                       [cut['position'], cut['position']],
                       'r-', linewidth=2.5, alpha=0.8)
                mid_x = (cut['start'] + cut['end']) / 2
                ax.text(mid_x, cut['position'], str(cut['order']),
                       ha='center', va='bottom', fontsize=11,
                       fontweight='bold', color='red',
                       bbox=dict(boxstyle='circle,pad=0.3', facecolor='white',
                                edgecolor='red', linewidth=2))
            else:
                ax.plot([cut['position'], cut['position']],
                       [cut['start'], cut['end']],
                       'b-', linewidth=2.5, alpha=0.8)
                mid_y = (cut['start'] + cut['end']) / 2
                ax.text(cut['position'], mid_y, str(cut['order']),
                       ha='left', va='center', fontsize=11,
                       fontweight='bold', color='blue',
                       bbox=dict(boxstyle='circle,pad=0.3', facecolor='white',
                                edgecolor='blue', linewidth=2))

        usage = total_area / (plate_width * plate_height) * 100
        print(f"\n  사용률: {usage:.1f}%")

        ax.set_xlim(0, plate_width)
        ax.set_ylim(0, plate_height)
        ax.set_aspect('equal')
        ax.set_xlabel('가로 (mm)')
        ax.set_ylabel('세로 (mm)')
        ax.set_title(f'원판 {plot_idx + 1} ({plate_width}×{plate_height})\n사용률: {usage:.1f}% | 절단: {len(plate["cuts"])}회',
                    fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.3)

    print(f"\n{'='*60}")
    print(f"총 사용 원판: {len(plates)}장")
    print(f"총 절단 횟수: {sum(len(p['cuts']) for p in plates)}회")

    legend_elements = [patches.Patch(facecolor=colors[ptype], alpha=0.7,
                                    edgecolor='black', label=ptype)
                      for ptype in sorted(piece_types)]
    fig.legend(handles=legend_elements, loc='upper center',
              bbox_to_anchor=(0.5, 0.98), ncol=len(piece_types))

    plt.tight_layout()
    plt.savefig('mdf_cutting_guillotine.png', dpi=150, bbox_inches='tight')
    print(f"\n시각화 파일 저장: mdf_cutting_guillotine.png")
    plt.show()


# 폰트 설정 초기화
setup_korean_font()
plt.rcParams['axes.unicode_minus'] = False
