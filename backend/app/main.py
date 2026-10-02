import logging
import os
import re
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator, Mapping
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


DEFAULT_CORS_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")
_ORIGIN = re.compile(r"^https?://[^/\s,]+$")


def cors_origins(env: Mapping[str, str] = os.environ) -> list[str]:
    """The frontend addresses the browser may call this API from: CORS_ORIGINS (comma separated, it replaces
    the local defaults), for example the deployed frontend's address. Wildcards and malformed entries stop the start."""
    raw = env.get("CORS_ORIGINS", "").strip()
    if not raw:
        return list(DEFAULT_CORS_ORIGINS)
    origins: list[str] = []
    for entry in raw.split(","):
        origin = entry.strip().rstrip("/")
        if origin == "*":
            raise RuntimeError("CORS_ORIGINS must not be '*': list the frontend address, e.g. https://cognify.example.com")
        if not _ORIGIN.match(origin):
            raise RuntimeError(
                f"CORS_ORIGINS has {entry.strip()!r}, which is not an origin. Use scheme and host only, "
                "comma separated, e.g. http://localhost:3000,https://cognify.example.com"
            )
        if origin not in origins:
            origins.append(origin)
    return origins


def tutor_mode(env: Mapping[str, str] = os.environ) -> str:
    """Which tutor serves the API: "offline" (DEMO_MODE=offline), "agent" (TUTOR_MODEL_ID set) or "stub"."""
    demo = env.get("DEMO_MODE", "").strip().lower()
    if demo not in ("", "off", "offline"):
        raise RuntimeError(f"DEMO_MODE is {demo!r}; use 'offline' to play the saved story, or leave it unset")
    if demo == "offline":
        return "offline"
    return "agent" if env.get("TUTOR_MODEL_ID") else "stub"


def check_tutor_config() -> str:
    """Say which tutor serves the API, and refuse to start a real tutor that cannot work."""
    mode = tutor_mode()
    if mode == "offline":
        # The saved story needs no network, no credentials and no model, so none of them are checked (F27)
        log.warning("tutor: OFFLINE DEMO (DEMO_MODE=offline): the saved Maria and Nikos story, no AI is called")
        return mode
    if mode == "stub":
        log.warning("tutor: StubTutor (TUTOR_MODEL_ID is not set; offline demo path)")
        return mode
    from app.ai_gateway.gateway import config_problems

    problems = config_problems("TUTOR_MODEL_ID")
    if problems:
        raise RuntimeError("TUTOR_MODEL_ID is set, so the real tutor is on, but: " + "; ".join(problems)
                           + ". Fix the configuration, set DEMO_MODE=offline, or unset TUTOR_MODEL_ID.")
    log.warning("tutor: AgentTutor (model %s, region %s)", os.environ["TUTOR_MODEL_ID"], os.environ["AWS_REGION"])
    return mode


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    check_tutor_config()
    autoseed()  # memory store only; restarting the backend resets the demo
    yield


app = FastAPI(title="FutureEd API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
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


# The real tutor when a model is configured; otherwise (or with DEMO_MODE=offline) the stub plays the saved story (F27).
if tutor_mode() == "agent":
    app.dependency_overrides[get_service] = get_agent_service


@app.get("/health")
def health() -> dict[str, str]:
    # Kept alongside /api/health for Docker and the curl check in CLAUDE.md
    return {"status": "ok"}
