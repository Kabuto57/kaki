"""Vercel serverless entrypoint.

The app itself lives in `backend/` and is unchanged. This only does two things:
put `backend/` on the import path, and mount the real app under `/api`, which is
the prefix the frontend already uses (`lib/api.js` defaults BASE to `/api`).

Serving both halves from one origin is why there is no CORS configuration in
production — the browser never makes a cross-origin request.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from fastapi import FastAPI  # noqa: E402

from app.main import app as kaki_app  # noqa: E402

app = FastAPI()
app.mount("/api", kaki_app)
