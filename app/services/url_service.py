import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import URL


ALPHABET = string.ascii_letters + string.digits
MAX_RETRIES = 5


@dataclass(frozen=True)
class CreatedURL:
    code: str
    expires_at: datetime | None


class ShortCodeGenerationError(Exception):
    pass


def create_short_url(
    db: Session,
    original_url: str,
    expires_in_seconds: int | None,
) -> CreatedURL:
    expires_at = None

    if expires_in_seconds is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=expires_in_seconds
        )

    for _ in range(MAX_RETRIES):
        code = "".join(secrets.choice(ALPHABET) for _ in range(8))

        url = URL(
            short_code=code,
            original_url=original_url,
            expires_at=expires_at,
        )

        db.add(url)

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()

            if (
                getattr(exc.orig, "sqlstate", None) == "23505"
                and getattr(
                    getattr(exc.orig, "diag", None),
                    "constraint_name",
                    None
                ) == "urls_short_code_key"
            ):
                continue

            raise

        return CreatedURL(
            code=code,
            expires_at=expires_at,
        )

    raise ShortCodeGenerationError(
        "Could not generate unique short code"
    )
