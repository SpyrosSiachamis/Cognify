from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.seed import autoseed
from app.user.errors import register_error_handlers
from app.user.router import router as user_router


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
register_error_handlers(app)
app.include_router(user_router)


@app.get("/health")
def health() -> dict[str, str]:
    # Kept alongside /api/health for Docker and the curl check in CLAUDE.md
    return {"status": "ok"}
