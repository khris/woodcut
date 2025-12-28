#!/usr/bin/env python3
"""CLI 진입점 - 서브커맨드 라우팅"""

import sys


def main():
    """CLI 진입점

    서브커맨드:
    - (없음): 대화형 재단 계획
    - web: 웹 서버 시작
    """
    if len(sys.argv) > 1 and sys.argv[1] == "web":
        from .web import run_server
        run_server()
    else:
        from .interactive import run_interactive
        run_interactive()


if __name__ == "__main__":
    main()
