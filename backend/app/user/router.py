from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.history import get_store
from app.session.schema import (
    AttemptResponse,
    ExitResponse,
    SessionStartRequest,
    SessionStartResponse,
    StudentAttempt,
)
from app.user.errors import ApiError
from app.user.schema import LearnerView, SessionTraceView, StrategyView, TraceExport, TraceIndex
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


# ---- development session trace: 404 unless DEBUG_TRACE is on ----


def _tracing(service: SessionService) -> SessionService:
    if not service.tracing:
        raise ApiError(404, "not_found", "Session tracing is off (set DEBUG_TRACE=true in development).")
    return service


@router.get("/session/{session_id}/debug-trace")
def session_trace(session_id: UUID, service: Service) -> SessionTraceView:
    return _tracing(service).trace_view(session_id)


@router.get("/debug-trace")
def trace_index(service: Service) -> TraceIndex:
    return _tracing(service).trace_index()


@router.get("/debug-trace/export")
def trace_export(service: Service, session_id: Annotated[list[UUID] | None, Query()] = None) -> TraceExport:
    """Every traced session (or the ones named), oldest first, for analysis across sessions."""
    return _tracing(service).trace_export(session_id)
