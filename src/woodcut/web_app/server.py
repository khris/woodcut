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


class StockInput(BaseModel):
    """원판 입력 모델"""
    width: int
    height: int
    count: int


class CuttingRequest(BaseModel):
    """재단 요청 모델"""
    stocks: list[StockInput]
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
    unplaced_pieces: list[dict] = []


@app.get("/")
async def read_root():
    """루트 경로 - index.html 반환"""
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/cut", response_model=CuttingResponse)
async def calculate_cutting(request: CuttingRequest):
    """재단 계획 계산 API"""
    if not request.pieces:
        raise HTTPException(status_code=400, detail="조각 정보가 없습니다")
    if not request.stocks:
        raise HTTPException(status_code=400, detail="원판 정보가 없습니다")

    try:
        pieces = [(p.width, p.height, p.count) for p in request.pieces]
        stocks = [(s.width, s.height, s.count) for s in request.stocks]

        if request.strategy == "region_based_split":
            packer = RegionBasedPackerWithSplit(stocks, request.kerf, request.allow_rotation)
        else:
            packer = RegionBasedPacker(stocks, request.kerf, request.allow_rotation)
        plates, unplaced = packer.pack(pieces)

        # free_spaces는 FreeSpace 객체 포함 내부 상태라 JSON 직렬화 불가 + 클라이언트 미사용
        for plate in plates:
            plate.pop('free_spaces', None)

        total_pieces = sum(p.count for p in request.pieces)
        placed_pieces = total_pieces - len(unplaced)

        return CuttingResponse(
            success=(len(unplaced) == 0),
            total_pieces=total_pieces,
            placed_pieces=placed_pieces,
            plates_used=len(plates),
            plates=plates,
            unplaced_pieces=unplaced,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 정적 파일 서빙 (HTML, CSS, JS)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR), follow_symlink=True), name="static")
