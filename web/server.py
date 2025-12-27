"""FastAPI 백엔드 서버 - Woodcut 웹 애플리케이션"""

import sys
from pathlib import Path

# woodcut 패키지를 import하기 위해 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from woodcut.strategies import RegionBasedPacker

app = FastAPI(title="Woodcut - MDF 재단 최적화")

# CORS 설정 (개발 환경용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PieceInput(BaseModel):
    """조각 입력 모델"""
    width: int
    height: int
    count: int


class CuttingRequest(BaseModel):
    """재단 요청 모델"""
    plate_width: int = 2440
    plate_height: int = 1220
    kerf: int = 5
    allow_rotation: bool = True
    pieces: list[PieceInput]


class CuttingResponse(BaseModel):
    """재단 응답 모델"""
    success: bool
    total_pieces: int
    placed_pieces: int
    plates_used: int
    plates: list[dict]


@app.get("/")
async def read_root():
    """루트 경로 - index.html 반환"""
    return FileResponse("index.html")


@app.post("/api/cut", response_model=CuttingResponse)
async def calculate_cutting(request: CuttingRequest):
    """재단 계획 계산 API"""
    try:
        # 입력 변환
        pieces = [(p.width, p.height, p.count) for p in request.pieces]

        if not pieces:
            raise HTTPException(status_code=400, detail="조각 정보가 없습니다")

        # 패킹 실행
        packer = RegionBasedPacker(
            request.plate_width,
            request.plate_height,
            request.kerf,
            request.allow_rotation
        )
        plates = packer.pack(pieces)

        # 통계 계산
        total_pieces = sum(p.count for p in request.pieces)
        placed_pieces = sum(len(plate['pieces']) for plate in plates)

        return CuttingResponse(
            success=True,
            total_pieces=total_pieces,
            placed_pieces=placed_pieces,
            plates_used=len(plates),
            plates=plates
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 정적 파일 서빙 (HTML, CSS, JS)
app.mount("/static", StaticFiles(directory="."), name="static")


if __name__ == "__main__":
    import uvicorn
    print("Starting Woodcut Web Server...")
    print("Open http://localhost:8000 in your browser")
    uvicorn.run(app, host="0.0.0.0", port=8000)
