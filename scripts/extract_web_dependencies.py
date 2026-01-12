#!/usr/bin/env python3
"""
app.js를 분석하여 필요한 Python 파일 목록을 추출하는 스크립트

GitHub Actions 워크플로우에서 사용하여 하드코딩 없이
동적으로 필요한 파일만 복사할 수 있도록 함.
"""

import re
import sys
from pathlib import Path


def extract_python_dependencies(app_js_path: str) -> list[str]:
    """app.js에서 fetch하는 .py 파일 경로를 추출
    
    Args:
        app_js_path: app.js 파일 경로
        
    Returns:
        .py 파일 상대 경로 리스트 (예: ['packing.py', 'region_based.py'])
    """
    with open(app_js_path, encoding='utf-8') as f:
        content = f.read()
    
    # fetch(`static/*.py`...) 패턴 찾기
    # 예: fetch(`static/packing.py?v=${Date.now()}`)
    pattern = r"fetch\([`'\"]static/([a-zA-Z0-9_]+\.py)"
    matches = re.findall(pattern, content)
    
    # 중복 제거 및 정렬
    return sorted(set(matches))


def find_python_files(py_filenames: list[str], src_root: Path) -> dict[str, Path]:
    """Python 파일명에 대응하는 실제 파일 경로를 찾음
    
    Args:
        py_filenames: .py 파일명 리스트 (예: ['packing.py', 'region_based.py'])
        src_root: 소스 루트 디렉토리 (예: src/woodcut/)
        
    Returns:
        {파일명: 전체경로} 딕셔너리
    """
    file_map = {}
    
    for filename in py_filenames:
        # 가능한 경로들을 탐색
        candidates = [
            src_root / filename,                      # 직접 위치
            src_root / 'strategies' / filename,       # strategies 하위
            src_root / 'packing.py',                  # packing.py는 루트에
        ]
        
        for candidate in candidates:
            if candidate.exists() and candidate.name == filename:
                file_map[filename] = candidate
                break
        else:
            print(f"경고: {filename}을 찾을 수 없습니다", file=sys.stderr)
    
    return file_map


def main():
    """메인 실행 함수"""
    # 프로젝트 루트 기준 경로 설정
    project_root = Path(__file__).parent.parent
    app_js_path = project_root / 'src/woodcut/web_app/static/app.js'
    src_root = project_root / 'src/woodcut'
    
    if not app_js_path.exists():
        print(f"오류: {app_js_path}를 찾을 수 없습니다", file=sys.stderr)
        sys.exit(1)
    
    # 1. app.js에서 필요한 .py 파일 추출
    py_files = extract_python_dependencies(str(app_js_path))
    
    if not py_files:
        print("오류: app.js에서 Python 파일을 찾을 수 없습니다", file=sys.stderr)
        sys.exit(1)
    
    print(f"발견된 Python 파일: {', '.join(py_files)}", file=sys.stderr)
    
    # 2. 실제 파일 경로 찾기
    file_map = find_python_files(py_files, src_root)
    
    if len(file_map) != len(py_files):
        print(f"경고: {len(py_files)}개 중 {len(file_map)}개만 찾음", file=sys.stderr)
    
    # 3. 상대 경로 출력 (워크플로우에서 사용)
    for filename, full_path in file_map.items():
        rel_path = full_path.relative_to(project_root)
        print(rel_path)


if __name__ == '__main__':
    main()
