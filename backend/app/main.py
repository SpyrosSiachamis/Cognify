from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.seed import autoseed


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    autoseed()  # memory store only; restarting the backend resets the demo
    yield


app = FastAPI(title="FutureEd API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
