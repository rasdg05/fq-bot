# Higgsfield → FQ pipeline

Higgsfield Cloud generates cinematic B-roll / product shots / AI backgrounds; this
repo turns them into branded, compliant, audio-mastered assets. Higgsfield makes
the raw footage — the brand, captions, legal line and audio stay here.

```
Higgsfield Cloud ──subscribe()──▶ result URLs ──download──▶
   video  → public/footage/hf-*.mp4      → clip `src` in ads/edl.ts (Remotion)
   images → products/social/assets/hf-*  → overlays, banners, carousel backgrounds
                          │
                          ▼
   Remotion + master audio + captions + CTA + disclaimer  →  final ad
```

Files: `scripts/higgsfield-gen.py` · `content/higgsfield-prompts.json`.

---

## Connect it (5 min)
1. Get an API key at **cloud.higgsfield.ai/api-keys** (format `key:secret`).
2. Install + set the key (never commit it):
   ```bash
   pip install higgsfield-client
   export HF_KEY="your-api-key:your-api-secret"
   ```
3. Generate:
   ```bash
   python3 marketing/scripts/higgsfield-gen.py --dry     # preview, generates nothing
   python3 marketing/scripts/higgsfield-gen.py           # all prompts
   python3 marketing/scripts/higgsfield-gen.py desk-broll  # one by id
   ```
   Images land in `products/social/assets/`, video in `public/footage/`.

## Use the output
- **Image** → drop into a carousel/banner HTML as a background, or as a Remotion
  overlay (`ClipSegment` `overlay`), or a new PFP/banner background.
- **Video** → add a scene to `ads/edl.ts` with `src: 'hf-desk'` (Remotion reads
  `public/footage/<name>.mp4`); it inherits the crossfades, captions and the
  English/Spanish audio master automatically.

## Video models
`content/higgsfield-prompts.json` ships confirmed **text-to-image**
(`bytedance/seedream/v4/text-to-image`). For video, copy `_video_example` into the
`assets` array and set `model` to the exact **image-to-video / text-to-video** slug
from your Higgsfield Cloud dashboard (the SDK also supports file uploads for
image-to-video — e.g. feed it a real photo of the Porsche).

## Rules
- Keep prompts free of on-screen numbers / profit claims — compliant copy is added
  in Remotion, not baked into AI footage.
- API keys via env / repo secret only. `HF_KEY` (or `HF_API_KEY` + `HF_API_SECRET`).
- Costs run on your Higgsfield plan (per-generation); the script generates on demand.
