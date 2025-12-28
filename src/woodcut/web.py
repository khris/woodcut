#!/usr/bin/env python3
"""웹 서버 진입점"""


def run_server():
    """웹 서버 시작"""
    import uvicorn
    from .web_app.server import app

    print("Starting Woodcut Web Server...")
    print("Open http://localhost:8000 in your browser")
    uvicorn.run(app, host="0.0.0.0", port=8000)
