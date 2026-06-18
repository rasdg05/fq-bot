# FQ · Estudio de anuncios (Remotion)

Edicion por codigo de creatividades verticales (9:16, 1080×1920) para Meta Ads.
Marca "Terminal / mesa de liquidez institucional" — espejo de `branding.py`.

## Que hay aqui

- **Generador de la app**: `AppShowcase` renderiza un mockup animado del bot FQ
  en Telegram (una senal SOL/USDT con el sistema de glifos real). Sustituye a
  la grabacion de pantalla.
- **Anuncios como datos**: cada version vive en `ads/edl.ts` como una lista de
  escenas (intro → hook → clip → showcase → CTA). Editas datos, no timelines.
- **Tu footage**: los clips se referencian por nombre + rango (in/out). Mientras
  no esten presentes se ven como "slate" de marca, asi previsualizas la
  estructura sin tener el video.

## Arranque

```bash
cd marketing
npm install
npm run dev        # abre Remotion Studio (preview en vivo de cada anuncio)
```

Edita `src/brand/tokens.ts`:
- `CTA_CONFIG`: pon el `botUsername`, el deep link `t.me/...` y tu `instagram`.
- `FOOTAGE_AVAILABLE`: dejalo en `false` hasta tener el footage cortado.

## Meter tu footage

1. Copia tus `.mp4` a `marketing/public/footage/` (mismo nombre que usa
   `ads/edl.ts`, p.ej. `NO.mp4`, `pix4brain28-AGS.mp4`).
   Sus IDs de Drive estan en `ads/footage.json`.
2. Genera contact sheets para elegir segundos:
   ```bash
   npm run ingest            # hojas de contacto en public/contact-sheets/
   npm run ingest -- --proxy # ademas proxies H.264 normalizados
   ```
3. Sube las hojas de contacto al chat → marcamos los `inSec`/`outSec` buenos en
   `ads/edl.ts`.
4. Pon `FOOTAGE_AVAILABLE = true` en `tokens.ts`.

## Renderizar

```bash
npm run render -- src/index.ts a1-no-al-ruido out/a1.mp4   # uno
npm run render:all                                          # todos -> out/
```

Salida: H.264 + faststart, lista para el subidor de Meta Ads.

## Cumplimiento (no opcional)

- Sin promesas de rentabilidad ni P&L. El microtexto legal (`Disclaimer`) es
  persistente y obligatorio — politica de productos financieros de Meta +
  `legal.py`.
- Ver `docs/META_ADS_PLAYBOOK.md` para placements, exclusion de tu feed,
  delimitacion geografica y la politica de cripto.
```
