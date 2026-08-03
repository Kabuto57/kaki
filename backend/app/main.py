"""Application assembly.

The one thing worth reading here is the exception handler. Domain code raises
`DomainError` subclasses that know nothing about HTTP; this maps them to status
codes in one place. The result is that every route is free of try/except noise
and every error response has the same shape, which is what makes the frontend's
error handling three lines instead of thirty.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import auth, games, me, ops, venues
from app.config import get_settings
from app.core.errors import DomainError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)

settings = get_settings()

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Fail loudly at boot rather than quietly running production on a key that
    is published in the repository."""
    if settings.is_production and "insecure" in settings.secret_key:
        raise RuntimeError(
            "SECRET_KEY is still the development default. Generate one with:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    if not settings.telegram_configured:
        logging.getLogger("kaki").warning(
            "Telegram is not configured — the API will serve whatever is already "
            "in the database, but no new games will arrive. See README."
        )
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Kaki",
    description=(
        "Search the Singapore badminton Telegram group by day, venue and time — "
        "the filters Telegram itself does not give you."
    ),
    version="1.0.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
async def handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


app.include_router(ops.router)
app.include_router(auth.router)
app.include_router(games.router)
app.include_router(venues.router)
app.include_router(me.router)
