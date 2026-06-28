# FQ — Video production & quality notes (process memory)

How the FQ ads are built, and the quality bar they must clear. Pipeline:
**Remotion (React/TS) for picture + ffmpeg for audio mastering + piper for EN
voiceover.** Everything compliant (no profit promises).

---

## 1. Architecture

- **EDL** (`ads/edl.ts`, `ads/edl-en.ts`): each ad = `intro` + `hook` + shared
  `BODY` + `cta`. Scenes carry `src`, `inSec/outSec`, `audio`, `emphasize`,
  `overlay`, `caption`. Cuts land on **complete sentences** (from the word-level
  transcript), never mid-phrase.
- **Composition** (`src/compositions/AdMovie.tsx`): `TransitionSeries` with 8-frame
  fade crossfades; dynamic music; captions; persistent disclaimer. Props:
  `frameMode` ('cover' 9:16 crop | 'band' full clip on brand bg), `lang` ('es'|'en'),
  `voiceover` (path to a mastered stem).
- **Brand strings** are language-aware via `tokens.ts` (`BRAND`/`BRAND_EN`,
  `COMMUNITY`/`COMMUNITY_EN`, `CTA_TEXT_EN`). Lesson: **every** on-screen string
  must be lang-gated — a missed `BRAND.desk` shipped "Mesa de liquidez" into an
  English cut. Sweep with `grep -nE '[áéíóúñ¿¡]' src/` before shipping EN.
- **Registration** (`src/Root.tsx`): ES ads → `{id}-cover` + `{id}-banda`;
  EN ads (`ADS_EN`) → same, with `lang:'en'` + `voiceover`.

Render/master/light: `scripts/render-en.sh` (render → `scripts/master.mjs` →
ffmpeg light). LIGHT = `scale=-2:1280, crf 30` (~4.5 MB, shareable on web/mobile).

---

## 2. Audio — the quality bar (this is where it's won or lost)

RasDG standard: *"bien sincronizado, bien cuidada la pista, sonoramente limpia,
entretenido, sin espacios muertos."* Hold to it.

### English voiceover (`scripts/voiceover-en.mjs`)
- **TTS:** piper (offline, free) voice `en_US-ryan-high` (natural male). Voice
  models live in `marketing/tts/` (gitignored, regenerable).
- **Sync:** each line is placed at its scene's **exact start frame**, computed
  the same way as AdMovie's `starts[]` (`cumsum(durations) − i·TRANSITION`), plus
  a **+0.367s LEAD** so the voice lands *with* the caption fade-in/crossfade — not
  ahead of the subtitles. Each line is measured to **fit inside its scene window**
  (no cutoffs, no overlap).
- **Captions:** hook uses a **plain** caption (not word-by-word) so the subs never
  drift against the spoken pace.
- **No dead air (critical):** the audio is one **self-contained stereo master** —
  voice + **sidechain-ducked music** + car ambience. The music sits up at a
  present "gap" level (`loudnorm I=-19`) and **ducks under the voice**
  (`sidechaincompress threshold=0.04:ratio=7:attack=12:release=340`), **swelling
  back in the gaps** so energy never drops. Verified: gaps ≈ speaking level
  (~-15 to -17 dB), never silence. In voiceover mode Remotion's separate music
  layer is **disabled** to avoid duplication.
- **Car engine rescued:** ambience from `IMG_1835` (the car B-roll), trimmed to
  the on-screen shot (`-ss 3 -t 3.6`), hi/lo-passed + faded, low under the voice.
- **Master chain:** voice → highpass 90, presence EQ @3.2k, comp, `loudnorm I=-15`;
  final mix → `alimiter limit=0.95`, `loudnorm I=-14:TP=-1:LRA=11`. True-peak safe.

### Spanish master (`scripts/master.mjs`)
highpass 85 · EQ (300/-2, 120/+1.5, 3500/+3) · treble 9k/+3 · aexciter ·
acompressor · alimiter · `loudnorm I=-13:TP=-1:LRA=10`. Dynamic music ducking
lives in AdMovie (music rises when no voice — "siempre una frecuencia presente").

---

## 3. Known limitations & honest notes

- **Lip-sync:** on talking-head clips the presenter's mouth speaks the original
  Spanish, so it cannot perfectly match the English VO. The voice tracks the
  **cuts and subtitles** cleanly (voiceover-ad standard). True mouth-match needs a
  reshoot in English or an AI lip-sync / ElevenLabs voice-clone pass (parked,
  by RasDG's "no gastar" constraint — keep as the next-step option).
- **Footage download:** claude.ai shows a player without a download button; export
  LIGHT versions and right-click "Save video as" in a browser.
- **Headless screenshots** don't trigger Framer-Motion whileInView — verify
  landing animations in a real browser, not via `--screenshot`.

---

## 4. Regenerate from scratch

```
cd marketing
node scripts/voiceover-en.mjs        # rebuild both EN masters (telegram + web)
bash scripts/render-en.sh            # render → master → LIGHT for all 4 EN cuts
node scripts/master.mjs <comp-id>    # master a single ES/EN composition
```

Deliverables index: `docs/PROCESS_MEMORY_INDEX.md`.
