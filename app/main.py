import secrets
import string
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import AnyHttpUrl, BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_db
from .models import URL

ALPHABET = string.ascii_letters + string.digits

app = FastAPI(title="URL Shortener")

class URLRequest(BaseModel):
    long_url: AnyHttpUrl
    expires_in_seconds: int | None = Field(
        default=None,
        gt=0,
        le=31_536_000,
    )


@app.post("/api/v1/urls", status_code=201)
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
        except IntegrityError:
            db.rollback()
            continue

        return {
            "code": code,
            "short_url": f"http://localhost:8000/{code}",
            "expires_at": expires_at,
        }

    raise HTTPException(
        status_code=503,
        detail="Could not generate unique short code"
    )


@app.get("/{code}")
def redirect(
    code: str,
    db: Session = Depends(get_db),
):
    url = db.scalar(
        select(URL).where(URL.short_code == code)
    )

    if url is None:
        raise HTTPException(
            status_code=404,
            detail="URL not found",
        )

    if (
        url.expires_at is not None
        and url.expires_at <= datetime.now(timezone.utc)
    ):
        raise HTTPException(
            status_code=410,
            detail="URL has expired",
        )

    return RedirectResponse(
        url=url.original_url, 
        status_code=302,
    )