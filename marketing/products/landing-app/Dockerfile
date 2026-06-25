# ---------- Stage 1: build the React frontend ----------
FROM node:20-slim AS frontend

WORKDIR /app/frontend

# Install deps first (better layer caching).
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

# Build. VITE_VIDEO_EMBED_URL is baked in at build time if provided.
COPY frontend/ ./
ARG VITE_VIDEO_EMBED_URL=""
ENV VITE_VIDEO_EMBED_URL=${VITE_VIDEO_EMBED_URL}
RUN npm run build


# ---------- Stage 2: python runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app

# Python deps.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Backend code + assets (ebook PDF).
COPY backend/ ./backend/

# Built frontend from stage 1. main.py also looks for ./backend/dist, but the
# repo layout (frontend/dist next to backend/) is reproduced here.
COPY --from=frontend /app/frontend/dist ./frontend/dist

EXPOSE 8000

# $PORT is provided by Railway at runtime; default 8000 locally.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
