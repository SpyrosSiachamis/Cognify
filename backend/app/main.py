import logging
import os
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from functools import lru_cache

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.history import get_store
from app.seed import autoseed
from app.user.errors import register_error_handlers
from app.user.router import get_service
from app.user.router import router as user_router
from app.user.service import SessionService


log = logging.getLogger(__name__)


def check_tutor_config() -> str:
    """Say which tutor serves the API, and refuse to start a real tutor that cannot work."""
    if not os.environ.get("TUTOR_MODEL_ID"):
        log.warning("tutor: StubTutor (TUTOR_MODEL_ID is not set; offline demo path)")
        return "stub"
    from app.ai_gateway.gateway import config_problems

    problems = config_problems("TUTOR_MODEL_ID")
    if problems:
        raise RuntimeError("TUTOR_MODEL_ID is set, so the real tutor is on, but: " + "; ".join(problems)
                           + ". Fix the configuration, or unset TUTOR_MODEL_ID to run the offline stub.")
    log.warning("tutor: AgentTutor (model %s, region %s)", os.environ["TUTOR_MODEL_ID"], os.environ["AWS_REGION"])
    return "agent"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    check_tutor_config()
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


@lru_cache
def get_agent_service() -> SessionService:
    from app.tutor.agent import AgentTutor

    store = get_store()
    return SessionService(AgentTutor(store), store)


# The real tutor when a model is configured; otherwise the stub keeps the demo offline (F27).
if os.environ.get("TUTOR_MODEL_ID"):
    app.dependency_overrides[get_service] = get_agent_service


@app.get("/health")
def health() -> dict[str, str]:
    # Kept alongside /api/health for Docker and the curl check in CLAUDE.md
    return {"status": "ok"}
