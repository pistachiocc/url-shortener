import secrets
import string

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, AnyHttpUrl
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_db
from .models import URL

ALPHABET = string.ascii_letters + string.digits

app = FastAPI(title="URL Shortener")

class URLRequest(BaseModel):
    long_url: AnyHttpUrl


@app.post("/api/v1/urls", status_code=201)
def create_url(
    request: URLRequest,
    db: Session = Depends(get_db),
):
    for _ in range(5):
        code = "".join(secrets.choice(ALPHABET) for _ in range(8))

        url = URL(
            short_code=code,
            original_url=str(request.long_url),
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
    original_url = db.scalar(
        select(URL.original_url).where(
            URL.short_code == code
        )
    )

    if original_url is None:
        raise HTTPException(
            status_code=404,
            detail="URL not found",
        )

    return RedirectResponse(
        url=original_url, 
        status_code=302,
    )