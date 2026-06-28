# FQ Marketing — Process memory index

Master index of everything built for the FQ / Fibonacci Cuántico marketing &
monetization system. Branch: `claude/marketing-video-editing-ijv4yv`. The real
bot code is never touched — all work lives under `marketing/`.

**Start here:**
- 🎙️ Voice / tone / brand curation → [`BRAND_VOICE_AND_STYLE.md`](./BRAND_VOICE_AND_STYLE.md)
- 🎬 Video production & quality bar → [`PRODUCTION_NOTES_VIDEO.md`](./PRODUCTION_NOTES_VIDEO.md)

---

## Deliverables (shippable artifacts)

### Lead magnet — ebooks
| Asset | Lang | Source | Render |
|---|---|---|---|
| "El sistema sobre el ego — 5 reglas" | ES | `products/lead-magnet/ebook.html` | `ebook.pdf` |
| **"Why you keep losing" (combined: short spine + pro substance)** | **EN** | `products/lead-magnet/ebook-en.html` | `ebook-en.pdf` → `deliverables/ebook/FQ-ebook-EN.pdf` |

The EN ebook merges the two improved free guides from the content branch
(`claude/contenido-ebook-quant`): the **short** "3 reglas" (accessible spine +
tone) and the **pro** "Cómo se construye una ventaja" (expectancy math, sizing,
backtest/overfitting/out-of-sample, secret-sauce close), primarily based on the
short version, in English, FQ identity matched.

### Video ads (car concept "g1")
LIGHT cuts in `deliverables/video/` (full masters regenerate via `scripts/render-en.sh`):
| File | Lang | CTA | Framing |
|---|---|---|---|
| `g1-perfil-ES-cover-LIGHT.mp4` | ES | landing | cover 9:16 |
| `g1-en-banda-LIGHT.mp4` | EN | Telegram DM | band |
| `g1-en-cover-LIGHT.mp4` | EN | Telegram DM | cover 9:16 |
| `g1-en-web-banda-LIGHT.mp4` | EN | landing/guide | band |
| `g1-en-web-cover-LIGHT.mp4` | EN | landing/guide | cover 9:16 |

EN audio: piper voiceover, +0.367s sync lead, sidechain-ducked continuous music
(no dead air), rescued car-engine ambience, mastered −14 LUFS. See production notes.

Spanish ad set (EDL `ads/edl.ts`): `g1-perfil` (→landing), `g1-dm` (→Telegram),
`g2-pierde`, `g3-roto`, `g4-producto`. EN set (`ads/edl-en.ts`): `g1-en`,
`g1-en-web`. Not yet in EN: g2/g3/g4 hook angles.

### Carousels (1080×1350)
| File | Theme |
|---|---|
| `products/carousel/edge.html` / `edge-en.html` | Edge verificable (BOFU) — ES + EN |
| `products/carousel/carousel.html` | Day-in-the-life agitation (5 slides) |
| `products/carousel/hooks.html` | 4 hook variants |
Captions: `CAPTIONS.md` (ES), copy + hooks `AD_COPY.md` / `AD_COPY_EN.md`.

### Landing
`products/landing-app/` — React+Tailwind+FastAPI (Railway), Resend PDF delivery.
`products/landing/index.html` — original static. Pending: deploy + Resend key +
intro video embed.

---

## Strategy & knowledge docs (`docs/`)
`MONETIZATION_PLAN.md` · `META_ADS_PLAYBOOK.md` · `META_API_SETUP.md` ·
`DM_ONBOARDING.md` · `AD_COPY.md` · `AD_COPY_EN.md` · `ROADMAP.md` ·
`VIDEO_SCRIPT_INTRO.md` · `COMPETITOR_ANALYSIS.md` · `CONTENT_IDEAS.md` ·
`BRAND_VOICE_AND_STYLE.md` · `PRODUCTION_NOTES_VIDEO.md` · this index.

Content source (the moat): `internal/_KNOWLEDGE_NOTES.md`, `RESEARCH.md`.

---

## Open / next steps
- EN versions of remaining hook angles (g2/g3/g4).
- AI lip-sync / voice-clone pass for true mouth-match (parked: cost).
- Deploy landing (Railway) + Resend + embed intro video.
- Launch Meta campaign via Ads Manager UI (all assets PAUSED by design; needs
  user credentials). API blocked: IG not page-backed for the app's ads use case.

## Compliance
Every asset: no profit promises, no %, no guarantees; persistent risk disclaimer;
process / risk-management / transparency focus. (Meta financial policy + `legal.py`.)
