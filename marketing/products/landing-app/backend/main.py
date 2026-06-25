"""FQ / Fibonacci Cuántico — lead-magnet backend.

FastAPI app that:
  - exposes POST /api/subscribe (store lead in SQLite + email the ebook via Resend)
  - exposes GET /api/health
  - serves the built React frontend (frontend/dist) with SPA fallback

Designed to run as a single Railway service:
    uvicorn backend.main:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

import base64
import logging
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from starlette.requests import Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fq.landing")

# --- Paths -----------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "leads.db"
EBOOK_PATH = BASE_DIR / "assets" / "ebook.pdf"
# frontend/dist sits next to the backend/ dir in the repo, and is copied next
# to it inside the Docker image too. Resolve both layouts.
DIST_DIR = (BASE_DIR.parent / "frontend" / "dist").resolve()
if not DIST_DIR.exists():
    DIST_DIR = (BASE_DIR / "dist").resolve()

# --- Config ----------------------------------------------------------------
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
FROM_EMAIL = os.getenv("FROM_EMAIL", "FQ <onboarding@resend.dev>").strip()
RESEND_ENDPOINT = "https://api.resend.com/emails"


# --- DB --------------------------------------------------------------------
def init_db() -> None:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source TEXT NOT NULL
            )
            """
        )
        conn.commit()


def store_lead(email: str, source: str) -> None:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            "INSERT INTO leads (email, created_at, source) VALUES (?, ?, ?)",
            (email, datetime.now(timezone.utc).isoformat(), source),
        )
        conn.commit()


# --- Email (Resend) --------------------------------------------------------
def _email_html() -> str:
    return """\
<div style="font-family:Inter,Arial,sans-serif;max-width:560px;margin:0 auto;color:#1a1f27;line-height:1.55;">
  <h2 style="margin:0 0 8px;">Aquí está tu guía 📩</h2>
  <p>¡Gracias por descargar la guía de <b>Fibonacci Cuántico (FQ)</b>!</p>
  <p>Adjunto te mando el PDF con las <b>5 reglas</b> para dejar de operar a corazonada y
  empezar con sistema: gestión de riesgo, R:R, tamaño de posición y el checklist de trade.</p>
  <p>Si tienes dudas o quieres entrar a la comunidad, escríbeme la palabra
  <b>«FQ»</b> por Telegram: <a href="https://t.me/RASDG05">@RASDG05</a>.<br>
  Y este es el bot de señales: <a href="https://t.me/rasdg_quantum_signals_bot">@rasdg_quantum_signals_bot</a>.</p>
  <p style="color:#5e6775;font-size:12px;border-top:1px solid #e3e6ea;padding-top:12px;margin-top:18px;">
    Contenido educativo. No es asesoría financiera ni recomendación de inversión. El trading conlleva
    alto riesgo: puedes perder todo tu capital. Rendimientos pasados no garantizan resultados futuros.
    — RasDG · Fibonacci Cuántico.
  </p>
</div>"""


async def send_ebook_email(to_email: str) -> bool:
    """Email the ebook PDF via Resend. Returns True if delivered.

    If RESEND_API_KEY is missing, log a warning and return False (dev fallback).
    """
    if not RESEND_API_KEY:
        logger.warning(
            "RESEND_API_KEY not set — skipping email delivery for %s (lead stored).",
            to_email,
        )
        return False

    if not EBOOK_PATH.exists():
        logger.error("Ebook PDF not found at %s — cannot attach.", EBOOK_PATH)
        return False

    pdf_b64 = base64.b64encode(EBOOK_PATH.read_bytes()).decode("ascii")
    payload = {
        "from": FROM_EMAIL,
        "to": [to_email],
        "subject": "Tu guía FQ: 5 reglas para operar con sistema",
        "html": _email_html(),
        "attachments": [
            {"filename": "FQ-guia-5-reglas.pdf", "content": pdf_b64}
        ],
    }
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(RESEND_ENDPOINT, json=payload, headers=headers)
        if resp.status_code >= 400:
            logger.error("Resend error %s: %s", resp.status_code, resp.text)
            return False
        return True
    except httpx.HTTPError as exc:
        logger.error("Resend request failed: %s", exc)
        return False


# --- App -------------------------------------------------------------------
app = FastAPI(title="FQ Landing", docs_url=None, redoc_url=None)


@app.on_event("startup")
def _startup() -> None:
    init_db()


# Also initialise at import time so the table exists even if the startup
# lifecycle event hasn't fired (e.g. under TestClient without a context manager).
init_db()


class SubscribeIn(BaseModel):
    email: EmailStr


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True}


@app.post("/api/subscribe")
async def subscribe(body: SubscribeIn) -> dict:
    email = str(body.email).strip().lower()
    try:
        store_lead(email, source="landing")
    except sqlite3.Error as exc:
        logger.error("Failed to store lead %s: %s", email, exc)
        raise HTTPException(status_code=500, detail="storage_error")

    delivered = await send_ebook_email(email)
    return {"ok": True, "delivered": delivered}


# --- Static frontend (mounted last so /api routes win) ---------------------
if DIST_DIR.exists():
    INDEX_FILE = DIST_DIR / "index.html"

    # Serve hashed assets etc. directly.
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str, request: Request) -> FileResponse:
        """SPA fallback: serve a real file if it exists, else index.html.

        API routes are declared above and take precedence; we still guard
        against /api paths leaking here.
        """
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not_found")
        candidate = (DIST_DIR / full_path).resolve()
        if (
            full_path
            and DIST_DIR in candidate.parents
            and candidate.is_file()
        ):
            return FileResponse(candidate)
        return FileResponse(INDEX_FILE)
else:
    logger.warning("frontend dist not found at %s — serving API only.", DIST_DIR)

    @app.get("/")
    async def _no_dist() -> JSONResponse:
        return JSONResponse(
            {"ok": True, "note": "Frontend build not found. Run the frontend build."}
        )
