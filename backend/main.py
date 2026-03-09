from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from api import router as api_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=
    [
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=
    [
        "*",
    ],
    allow_headers=
    [
        "*",
    ],
)

app.include_router(api_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
