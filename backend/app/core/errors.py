"""Unified error responses, request tracing middleware, and safe server logging."""
from __future__ import annotations

import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("t1shop.api")

_HTTP_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
}


def configure_logging() -> None:
    """Configure a consistent log format for request tracing without duplicating handlers."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    else:
        root.setLevel(logging.INFO)


def _error_payload(
    *,
    code: str,
    message: str,
    details: object = None,
    request_id: str | None = None,
) -> dict:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
        "request_id": request_id,
    }


def _clean_validation_message(raw_message: object) -> str:
    text = str(raw_message or "Dữ liệu không hợp lệ.")
    if text.startswith("Value error, "):
        return text[len("Value error, "):]
    return text


def register_middleware_and_handlers(app: FastAPI) -> None:
    """Attach tracing middleware and uniform validation/HTTP/system exception handlers."""
    configure_logging()

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        request_id = uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()
        client_ip = request.client.host if request.client else "-"
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Unhandled middleware error request_id=%s method=%s path=%s client=%s",
                request_id,
                request.method,
                request.url.path,
                client_ip,
            )
            response = JSONResponse(
                status_code=500,
                content=_error_payload(
                    code="INTERNAL_ERROR",
                    message="Đã xảy ra lỗi hệ thống.",
                    request_id=request_id,
                ),
            )
        duration_ms = (time.perf_counter() - started) * 1000.0
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_id=%s method=%s path=%s status=%s duration_ms=%.2f client=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            client_ip,
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(part) for part in error.get("loc", ())),
                "message": _clean_validation_message(error.get("msg")),
                "code": str(error.get("type", "invalid")),
            }
            for error in exc.errors()
        ]
        request_id = getattr(request.state, "request_id", None)
        logger.info(
            "Validation error request_id=%s method=%s path=%s error_count=%s",
            request_id,
            request.method,
            request.url.path,
            len(errors),
        )
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                code="VALIDATION_ERROR",
                message="Dữ liệu gửi lên không hợp lệ.",
                details=errors,
                request_id=request_id,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        if exc.status_code >= 500:
            logger.error(
                "HTTP server error request_id=%s method=%s path=%s status=%s",
                request_id,
                request.method,
                request.url.path,
                exc.status_code,
            )
            code = "SERVICE_UNAVAILABLE" if exc.status_code == 503 else "INTERNAL_ERROR"
            message = "Đã xảy ra lỗi hệ thống."
            details = None
        else:
            code = _HTTP_ERROR_CODES.get(exc.status_code, "REQUEST_ERROR")
            message = (
                exc.detail
                if isinstance(exc.detail, str)
                else "Yêu cầu không thể xử lý."
            )
            details = None if isinstance(exc.detail, str) else exc.detail

        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content=_error_payload(
                code=code,
                message=message,
                details=details,
                request_id=request_id,
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.exception(
            "Unhandled request error request_id=%s method=%s path=%s",
            request_id,
            request.method,
            request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                code="INTERNAL_ERROR",
                message="Đã xảy ra lỗi hệ thống.",
                request_id=request_id,
            ),
        )
