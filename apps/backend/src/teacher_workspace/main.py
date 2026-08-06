import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from teacher_workspace import __version__
from teacher_workspace.auth import router as auth_router
from teacher_workspace.config import get_settings
from teacher_workspace.db import dispose_engine
from teacher_workspace.health import router as health_router
from teacher_workspace.phase1 import router as phase1_router
from teacher_workspace.phase2 import router as phase2_router
from teacher_workspace.phase3 import router as phase3_router
from teacher_workspace.phase4 import router as phase4_router
from teacher_workspace.phase5 import router as phase5_router
from teacher_workspace.phase7 import router as phase7_router
from teacher_workspace.phase8 import router as phase8_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version=__version__,
    docs_url="/api/docs" if settings.app_env != "production" else None,
    openapi_url="/api/openapi.json" if settings.app_env != "production" else None,
    lifespan=lifespan,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.trusted_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(phase1_router)
app.include_router(phase2_router)
app.include_router(phase3_router)
app.include_router(phase4_router)
app.include_router(phase5_router)
app.include_router(phase7_router)
app.include_router(phase8_router)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next: Any) -> Any:
    candidate = request.headers.get("X-Request-ID", "")
    request_id = (
        candidate if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", candidate) else str(uuid.uuid4())
    )
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


def error_body(request: Request, code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "request_id": getattr(request.state, "request_id", str(uuid.uuid4())),
        "details": details,
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict):
        code = str(detail.get("code", "HTTP_ERROR"))
        message = str(detail.get("message", "Request failed"))
        details = detail.get("details")
    else:
        code, message, details = "HTTP_ERROR", str(detail), None
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(request, code, message, details),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_body(
            request,
            "VALIDATION_ERROR",
            "Request validation failed",
            jsonable_encoder(exc.errors()),
        ),
    )


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, _: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=error_body(request, "INTERNAL_ERROR", "服务器暂时无法完成请求"),
    )
