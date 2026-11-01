import string
import logging
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import AnyHttpUrl, BaseModel, Field
from sqlalchemy.orm import Session
from redis import Redis

from .services.url_service import ShortCodeGenerationError, create_short_url
from .services.redirect_service import URLExpiredError, URLNotFoundError, get_original_url
from .database import get_db
from .cache import get_cache
from .rate_limit import enforce_create_rate_limit
from .logging_config import configure_logging

ALPHABET = string.ascii_letters + string.digits

configure_logging()

app = FastAPI(title="URL Shortener")

request_logger = logging.getLogger("app.http")


@app.middleware("http")
async def log_http_requests(request: Request, call_next):
    start_time = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start_time) * 1000

        request_logger.exception(
            "HTTP request failed",
            extra={
                "event": "http_request_error",
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "duration_ms": round(duration_ms, 2),
            },
        )
        raise

    duration_ms = (time.perf_counter() - start_time) * 1000

    request_logger.info(
        "HTTP request completed",
        extra={
            "event": "http_request",
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
        },
    )

    return response




class URLRequest(BaseModel):
    long_url: AnyHttpUrl
    expires_in_seconds: int | None = Field(
        default=None,
        gt=0,
        le=31_536_000,
    )


@app.post(
    "/api/v1/urls",
    status_code=201,
    dependencies=[Depends(enforce_create_rate_limit)],
)
def create_url(
    request: URLRequest,
    db: Session = Depends(get_db),
):
    try:
        result = create_short_url(
            db=db,
            original_url=str(request.long_url),
            expires_in_seconds=request.expires_in_seconds,
        )
    except ShortCodeGenerationError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    return {
        "code": result.code,
        "short_url": f"http://localhost:8000/{result.code}",
        "expires_at": result.expires_at,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/{code}")
def redirect(
    code: str,
    db: Session = Depends(get_db),
    cache: Redis = Depends(get_cache),
):
    try:
        original_url = get_original_url(
            code=code,
            db=db,
            cache=cache,
        )

    except URLNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except URLExpiredError as exc:
        raise HTTPException(
            status_code=410,
            detail=str(exc),
        ) from exc

    return RedirectResponse(
        url=original_url,
        status_code=302,
    )
