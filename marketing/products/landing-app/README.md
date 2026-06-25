# FQ · Fibonacci Cuántico — Landing (lead magnet)

Production-ready lead-magnet landing page for **FQ / Fibonacci Cuántico** (trader Diego Gallegos, alias **RasDG**).

- **Frontend:** React + TypeScript + Vite + Tailwind CSS + Framer Motion. Mobile-first, pixel-perfect, dark/premium. Fonts (Inter + JetBrains Mono) bundled via `@fontsource` — no runtime CDN.
- **Backend:** Python FastAPI. Serves the built frontend **and** exposes `POST /api/subscribe` (stores the lead in SQLite and emails the ebook PDF via [Resend](https://resend.com/docs)).
- **Deploy:** a single Railway service (multi-stage Dockerfile).

```
landing-app/
├── frontend/            # Vite + React + Tailwind app
│   └── src/
│       ├── components/  # Hero, OfferCard, ValueGrid, Transparency, ...
│       └── lib/         # motion presets, constants (links, video url)
├── backend/
│   ├── main.py          # FastAPI app + /api/subscribe + static serving
│   ├── requirements.txt
│   └── assets/ebook.pdf # the guide that gets emailed
├── Dockerfile           # node build -> python runtime
├── railway.json         # Railway build/deploy config
└── Procfile             # fallback start command
```

---

## Local development

Two terminals.

**Backend** (port 8000):

```bash
cd marketing/products/landing-app
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
# from the landing-app/ dir so `backend.main` imports correctly:
uvicorn backend.main:app --reload --port 8000
```

**Frontend** (port 5173, proxies `/api` → 8000):

```bash
cd marketing/products/landing-app/frontend
npm install
npm run dev
```

Open http://localhost:5173.

Without `RESEND_API_KEY`, `/api/subscribe` still **stores the lead** and returns
`{"ok": true, "delivered": false}` (dev fallback — it does not crash).

### Build the frontend once and let FastAPI serve everything

```bash
cd marketing/products/landing-app/frontend && npm run build   # -> frontend/dist
cd .. && uvicorn backend.main:app --port 8000                 # serves SPA + API at :8000
```

---

## Environment variables

| Variable                | Required | Purpose                                                                          |
| ----------------------- | -------- | -------------------------------------------------------------------------------- |
| `RESEND_API_KEY`        | for email delivery | Resend API key. If missing, leads are still stored; email is skipped. |
| `FROM_EMAIL`            | recommended | Verified sender, e.g. `FQ <hola@tudominio.com>`. Default: `FQ <onboarding@resend.dev>`. |
| `VITE_VIDEO_EMBED_URL`  | optional | Intro video **embed** URL (YouTube/Vimeo). Baked in at frontend build time. |
| `PORT`                  | provided by Railway | Port uvicorn binds to. |

> `FROM_EMAIL` must use a domain you've verified in Resend (or `onboarding@resend.dev` for testing). See https://resend.com/docs.

---

## Deploy to Railway (single service)

1. **Create the project.** Railway → **New Project → Deploy from GitHub repo** → pick this repo.
2. **Set the Root Directory.** Service → **Settings → Root Directory** = `marketing/products/landing-app`.
   This makes Railway use this folder's `Dockerfile` / `railway.json`.
3. **Builder.** It auto-detects the `Dockerfile`. (railway.json already pins `DOCKERFILE`.)
4. **Set environment variables** (Service → **Variables**):
   - `RESEND_API_KEY` = your Resend key
   - `FROM_EMAIL` = `FQ <hola@tudominio.com>`
   - `VITE_VIDEO_EMBED_URL` = (optional) e.g. `https://www.youtube.com/embed/XXXXXXXX`
     - Note: this is a **build-time** var for Vite. After changing it, **redeploy** so the frontend rebuilds.
5. **Deploy.** Railway builds the image (node builds `dist`, python runtime serves it) and starts
   `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`. Health check: `/api/health`.
6. **Get the public URL.** Service → **Settings → Networking → Generate Domain**
   → you get `https://<name>.up.railway.app`.
7. **Custom domain (optional).** Same **Networking** panel → **Custom Domain** → add e.g.
   `guia.tudominio.com`, then create the shown **CNAME** record at your DNS provider. Wait for it to verify.

### Test it

```bash
# health
curl https://<your-domain>/api/health
# -> {"ok":true}

# subscribe (stores lead + emails the ebook if RESEND_API_KEY is set)
curl -X POST https://<your-domain>/api/subscribe \
  -H "Content-Type: application/json" \
  -d '{"email":"tucorreo@gmail.com"}'
# -> {"ok":true,"delivered":true}    (delivered=false if no RESEND_API_KEY)
```

---

## The ad funnel

Your **A1 ad** (Instagram Reels, etc.) sends people to this URL (the Railway domain or your custom
domain). They watch the intro video, drop their email to get the free guide (delivered by email),
or jump straight into Telegram by writing **«FQ»** to [@RASDG05](https://t.me/RASDG05).

---

## Swapping in the intro video

The hero shows a tasteful placeholder until you provide a video.

- **Production (Railway):** set `VITE_VIDEO_EMBED_URL` to an **embed** URL and redeploy:
  - YouTube: `https://www.youtube.com/embed/VIDEO_ID`
  - Vimeo: `https://player.vimeo.com/video/VIDEO_ID`
- **Local:** create `frontend/.env` with `VITE_VIDEO_EMBED_URL=https://www.youtube.com/embed/VIDEO_ID`
  and rebuild/restart the dev server.

When set, the slot renders a responsive 16:9 iframe; when empty, the placeholder + play button shows.

---

## Notes on the lead database

Leads are stored in `backend/leads.db` (SQLite). On Railway's ephemeral filesystem this resets on
redeploy — fine as a backup, since the primary delivery is the **email**. For durable storage,
attach a Railway Volume mounted at `backend/` or swap to Postgres later.
