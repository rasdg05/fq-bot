# Clean cuts — trimmed source, NO overlays / captions / graphics

For the other editor: these are the exact segments we cut for the FQ ads, with the
**original camera audio**, and **nothing added** — no car overlay, no captions, no
brand graphics, no audio mastering. Raw trimmed clips, ready to re-edit.

Filenames: `<clip>_<inSec>-<outSec>_<role-label>.mp4`

| File | Role in the ad | Source clip · in–out (s) |
|---|---|---|
| `IMG_1846_1.3-8.5_hook-carro_por-que-la-mayoria.mp4` | Hook (car) — "why most will never drive one of these" | IMG_1846 · 1.3–8.5 |
| `IMG_1849_12.0-16.8_body_el-mercado-no-te-robo.mp4` | Body — "the market didn't rob you" | IMG_1849 · 12.0–16.8 |
| `IMG_1848_7.4-11.0_body_compran-por-corazonada.mp4` | Body — "they buy on a feeling, sell on fear" | IMG_1848 · 7.4–11.0 |
| `IMG_1846_9.3-15.85_body_apoyate-en-sistema-FQ.mp4` | Body — "lean on a system: Fibonacci Cuántico" | IMG_1846 · 9.3–15.85 |
| `IMG_1835_3.0-6.0_broll-porsche.mp4` | Car B-roll (used as the hook overlay) | IMG_1835 · 3.0–6.0 |
| `IMG_5979_0.3-5.3_hook_la-mayoria-pierde.mp4` | Hook B — "why most people lose" | IMG_5979 · 0.3–5.3 |
| `IMG_1844_3.0-6.7_hook_sigues-igual-de-roto.mp4` | Hook C — "years in, still broke" | IMG_1844 · 3.0–6.7 |
| `IMG_1851_0.9-7.5_hook_bot-entrada-stop-target.mp4` | Hook D — "a bot that gives you entry/stop/target" | IMG_1851 · 0.9–7.5 |

## Where the rest lives
- **Full uncut source clips** (all 12 reels): Google Drive → folder
  **"FQ - Anuncios (fuente reels)"** (`IMG_*.MOV/.mp4`). Locally they sit in
  `marketing/public/footage/` but that folder is **gitignored** (too big for the
  repo), so pull them from Drive.
- **The edit decision list** (every cut's in/out + intent, per ad): `marketing/ads/edl.ts`
  (Spanish) and `marketing/ads/edl-en.ts` (English voiceover version).
- **Finished ads** (WITH overlays, captions, brand, mastered audio):
  `marketing/deliverables/video/` (the `*-LIGHT.mp4` files).
- **Rebuild anything**: Remotion project in `marketing/` (`npm run render`), audio
  masters via `scripts/master.mjs` / `scripts/voiceover-en.mjs`.
