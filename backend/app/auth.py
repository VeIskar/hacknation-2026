"""JWT na API (Treść pkt 5; SPEC.md, „API contract”, 401).

Przy JWT_ENABLED=true POST /api/forms wymaga nagłówka `Authorization: Bearer <JWT_TOKEN>`.
GET /health zostaje otwarte. Token wystawia skrypt:

    JWT_SECRET=... python -m app.auth token [--hours 24]
"""

import argparse
import sys
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, Request

from app.config import Settings, get_settings
from app.errors import AppError

MSG_UNAUTHORIZED = "Brak tokenu dostępu albo token jest nieważny."
# Sekret jest wspólny dla serwera i skryptu, więc tylko HMAC. Bez "none" i bez kluczy publicznych.
# RFC 7518, 3.2: klucz HMAC co najmniej tak długi jak skrót. Wartość: minimum bajtów sekretu.
MIN_SECRET_BYTES = {"HS256": 32, "HS384": 48, "HS512": 64}
SUBJECT = "api"


class AuthError(AppError):
    """Brak tokenu, zły token albo wygasł (401). main.py dodaje nagłówek WWW-Authenticate."""

    status_code = 401
    allowed_status_codes = frozenset({401})


def _signing_params(settings: Settings) -> tuple[str, str]:
    """Sekret i algorytm. Przy starcie zła konfiguracja zatrzymuje API (check_config); później to 500, nie błąd klienta."""
    secret, algorithm = settings.jwt_secret, settings.jwt_algorithm
    if not secret:
        raise RuntimeError("JWT_SECRET jest pusty")
    if algorithm not in MIN_SECRET_BYTES:
        # Bez wartości: sekret wklejony w złą zmienną trafiłby do logu (jak w config.py, D9 pkt 3).
        raise RuntimeError(f"JWT_ALGORITHM ma być jednym z {sorted(MIN_SECRET_BYTES)}")
    if len(secret.encode()) < MIN_SECRET_BYTES[algorithm]:
        raise RuntimeError(f"JWT_SECRET dla {algorithm} ma mieć co najmniej {MIN_SECRET_BYTES[algorithm]} bajtów")
    return secret, algorithm


def check_config(settings: Settings) -> None:
    """Przy starcie API: przy JWT_ENABLED=true zła konfiguracja zatrzymuje start, zamiast dawać 500 przy żądaniu."""
    if settings.jwt_enabled:
        _signing_params(settings)


def _bearer_token(header: str | None) -> str:
    scheme, _, token = (header or "").strip().partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token or " " in token:
        raise AuthError(detail=MSG_UNAUTHORIZED)
    return token


def verify_token(token: str, settings: Settings) -> dict:
    secret, algorithm = _signing_params(settings)
    try:
        return jwt.decode(token, secret, algorithms=[algorithm], options={"require": ["exp"]})
    except jwt.InvalidTokenError as exc:
        raise AuthError(detail=MSG_UNAUTHORIZED) from exc


def require_token(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> None:
    """Zależność FastAPI. Działa przed odczytem pliku, więc 401 ma pierwszeństwo przed 400/413/415."""
    if not settings.jwt_enabled:
        return
    verify_token(_bearer_token(request.headers.get("authorization")), settings)


def create_token(settings: Settings, *, hours: float = 24, now: datetime | None = None) -> str:
    if hours <= 0:
        raise ValueError("hours ma być większe od zera")
    secret, algorithm = _signing_params(settings)
    issued = now or datetime.now(UTC)
    claims = {"sub": SUBJECT, "iat": issued, "exp": issued + timedelta(hours=hours)}
    return jwt.encode(claims, secret, algorithm=algorithm)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.auth", description="Token JWT dla API.")
    commands = parser.add_subparsers(dest="command", required=True)
    token = commands.add_parser("token", help="wypisz token podpisany JWT_SECRET")
    token.add_argument("--hours", type=float, default=24, help="ważność w godzinach (domyślnie 24)")
    args = parser.parse_args(argv)
    try:
        print(create_token(Settings.from_env(), hours=args.hours))
    except (RuntimeError, ValueError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
