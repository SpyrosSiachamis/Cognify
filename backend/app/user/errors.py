from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.user.schema import ErrorBody, ErrorResponse


class ApiError(Exception):
    """Raised anywhere in the user module; rendered as the contract's error shape."""

    def __init__(self, status: int, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.body = ErrorBody(code=code, message=message, retryable=retryable)


def _response(status: int, code: str, message: str, retryable: bool = False) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, retryable=retryable))
    return JSONResponse(status_code=status, content=body.model_dump())


def register_error_handlers(app: FastAPI) -> None:
    """Every error leaves the API in the one contract shape (API_CONTRACT.md, error shape)."""

    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _response(exc.status, exc.body.code, exc.body.message, exc.body.retryable)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0]
        parts = [str(part) for part in first["loc"] if part not in ("body", "path", "query") and not isinstance(part, int)]
        where = ".".join(parts)
        # The message names the field and the rule, never the submitted value (it may be the student's text)
        return _response(422, "invalid_request", f"{where or 'request body'}: {first['msg']}")

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed"}
        return _response(exc.status_code, codes.get(exc.status_code, "http_error"), str(exc.detail))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        # A bug must not leak a traceback to the student; the server still logs it
        return _response(500, "internal_error", "Something went wrong. Please try again.", retryable=True)
