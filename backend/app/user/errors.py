from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.user.schema import ErrorBody, ErrorResponse


class ApiError(Exception):
    """Raised anywhere in the user module; rendered as the contract's error shape."""

    def __init__(self, status: int, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.body = ErrorBody(code=code, message=message, retryable=retryable)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=ErrorResponse(error=exc.body).model_dump())
