import secrets
import string
import json
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import AnyHttpUrl, BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from redis import Redis
from redis.exceptions import RedisError

from .database import get_db
from .models import URL
from .cache import get_cache
from .rate_limit import enforce_create_rate_limit

ALPHABET = string.ascii_letters + string.digits

app = FastAPI(title="URL Shortener")

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
    expires_at = None

    if request.expires_in_seconds is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=request.expires_in_seconds
        )

    for _ in range(5):
        code = "".join(secrets.choice(ALPHABET) for _ in range(8))

        url = URL(
            short_code=code,
            original_url=str(request.long_url),
            expires_at=expires_at,
        )

        db.add(url)

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()

            if (
                getattr(exc.orig, "sqlstate", None) == "23505"
                and getattr(exc.orig.diag, "constraint_name", None)
                == "urls_short_code_key"
            ):
                continue

            raise

        return {
            "code": code,
            "short_url": f"http://localhost:8000/{code}",
            "expires_at": expires_at,
        }

    raise HTTPException(
        status_code=503,
        detail="Could not generate unique short code"
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/{code}")
def redirect(
    code: str,
    db: Session = Depends(get_db),
    cache: Redis = Depends(get_cache),
):
    cache_key = f"url:{code}"

    # 1. Try Redis first
    try:
        cached = cache.get(cache_key)
    except RedisError:
        cached = None

    if  cached is not None:
        try:
            data = json.loads(cached)

            expires_at = (
                datetime.fromisoformat(data["expires_at"])
                if data["expires_at"] is not None
                else None
            )

            if expires_at is not None and expires_at <= datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=410,
                    detail="URL has expired",
                )

            return RedirectResponse(
                url=data["original_url"],
                status_code=302,
            )
        except (ValueError, TypeError, KeyError):
            # Invalid cache entry: fall back to database
            pass

    # 2. Cache Miss: query PostgreSQL
    url = db.scalar(
        select(URL).where(URL.short_code == code)
    )

    if url is None:
        raise HTTPException(
            status_code=404,
            detail="URL not found",
        )

    if url.expires_at is not None and url.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=410,
            detail="URL has expired",
        )

    # 3. Calculate cache TTL
    cache_ttl = 3600

    if url.expires_at is not None:
        remaining = (url.expires_at - datetime.now(timezone.utc)).total_seconds()
        cache_ttl = min(cache_ttl, int(remaining))

    # 4. Populate Redis
    if cache_ttl > 0:
        data = {
            "original_url": url.original_url,
            "expires_at": (
                url.expires_at.isoformat()
                if url.expires_at is not None
                else None
            ),
        }

        try:
            cache.set(
                cache_key,
                json.dumps(data),
                ex=cache_ttl,
            )
        except RedisError:
            pass

    return RedirectResponse(
        url=url.original_url, 
        status_code=302,
    )