from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.history import get_store
from app.session.schema import (
    AttemptResponse,
    ExitResponse,
    SessionStartRequest,
    SessionStartResponse,
    StudentAttempt,
)
from app.user.schema import LearnerView, StrategyView
from app.user.service import SessionService
from app.user.stub_tutor import StubTutor

router = APIRouter(prefix="/api")


@lru_cache
def get_service() -> SessionService:
    # Swap StubTutor for the real agent here once it exists
    return SessionService(StubTutor(), get_store())


Service = Annotated[SessionService, Depends(get_service)]


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/session")
async def start_session(body: SessionStartRequest, service: Service) -> SessionStartResponse:
    return await service.start(body)


@router.post("/session/{session_id}/attempt")
async def attempt(session_id: UUID, body: StudentAttempt, service: Service) -> AttemptResponse:
    return await service.attempt(session_id, body.text)


@router.post("/session/{session_id}/exit")
async def exit_session(session_id: UUID, service: Service) -> ExitResponse:
    return await service.exit(session_id)


@router.get("/learner/{student_id}")
def learner(student_id: UUID, service: Service) -> LearnerView:
    return service.learner_view(student_id)


@router.get("/strategies/{student_id}")
def strategies(student_id: UUID, service: Service) -> StrategyView:
    return service.strategy_view(student_id)
