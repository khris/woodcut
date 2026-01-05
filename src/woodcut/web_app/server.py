"""FastAPI 백엔드 서버 - Woodcut 웹 애플리케이션"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..strategies import RegionBasedPacker
from ..strategies.region_based_split import RegionBasedPackerWithSplit

# 파일 디렉토리 경로
CURR_DIR = Path(__file__).parent
STATIC_DIR = CURR_DIR / "static"

app = FastAPI(title="Woodcut - 목재 재단 최적화")

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
    strategy: str = "region_based"
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
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/cut", response_model=CuttingResponse)
async def calculate_cutting(request: CuttingRequest):
    """재단 계획 계산 API"""
    try:
        # 입력 변환
        pieces = [(p.width, p.height, p.count) for p in request.pieces]

        if not pieces:
            raise HTTPException(status_code=400, detail="조각 정보가 없습니다")

        # 전략 선택에 따라 패커 생성
        if request.strategy == "region_based_split":
            packer = RegionBasedPackerWithSplit(
                request.plate_width,
                request.plate_height,
                request.kerf,
                request.allow_rotation
            )
        else:
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
app.mount("/static", StaticFiles(directory=str(STATIC_DIR), follow_symlink=True), name="static")
