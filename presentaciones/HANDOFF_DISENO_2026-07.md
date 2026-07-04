# PROMPT MAESTRO — Generar arte de marca (Higgsfield) y aplicarlo a TODO

> Pega esto en una sesión NUEVA de Claude Code (con Higgsfield MCP conectado). Cubre el
> proceso completo: generar el arte, y aplicarlo a los PDFs y a la página. Ejecuta por fases,
> commiteando al final de cada una.

---

## Misión
Generar el arte visual de marca de **FQ** con Higgsfield y aplicarlo de forma cohesiva a
(1) el Manual & FAQ en PDF, (2) los decks de `presentaciones/`, y (3) la página/terminal
(`cockpit.html`). Marca curada oro/Solana, cinematográfica, **sin texto en las imágenes**
(el wordmark y los títulos se ponen como texto HTML encima).

## Antes de empezar — LEE estos archivos (son la fuente de verdad, no reinventes)
- `presentaciones/manual-faq-fq-2026-07.html` → **referencia de marca** (tokens CSS, marca φ
  en SVG, tipografía, layout). Copia ese sistema.
- `presentaciones/marketing-kit-2026-07.md` → **prompts de Higgsfield** (bloque de estilo
  reusable + negative + 4 prompts A–D) y el guion de video.

## Marca LOCK (verifica contra el manual)
```
bg #050705 · panel #0a0f0b/#0c1310 · ink #e9e7e0 · muted #8a9690
oro #d4af37 · goldline #c9a227 · Solana #9945FF → #14F195
marca φ: anillo dorado (stroke #c9a227) + arco Solana (gradiente) + glifo φ oro, en SVG
tipografía: ui-monospace para kickers/labels (uppercase, tracking .18–.38em) · Georgia serif para titulares/cuerpo
voz: institucional, seca, anti-humo · "medida o muerte" / "la disciplina es el producto"
```

---

## FASE 1 — Generar el arte (Higgsfield)
1. Usa **modelo `soul_2`** (cinematic). Corre **`get_cost:true` primero** (preflight barato)
   antes de cada `generate_image`; no quemes créditos de más (~0.12 cr/imagen).
2. Genera los prompts **A, B, C, D** del `marketing-kit-2026-07.md` (bloque STYLE + negative
   **"no text/letters/words/logos/faces"** SIEMPRE). Aspectos: A y B en **3:4** (portadas),
   C en **16:9**, D en **9:16**.
3. Genera 2 variaciones de A (es la portada hero). Elige la mejor y **`upscale_image`** la ganadora.
4. **Descarga** los assets elegidos a `presentaciones/assets/` (crea la carpeta). Nómbralos
   `hero.jpg` (A), `alt.jpg` (B), `gate.jpg` (C), `social.jpg` (D). Optimiza a <300KB c/u
   (calidad ~82) para que embeban sin inflar.
5. Commit: `assets(marca): arte Higgsfield generado (hero/alt/gate/social)`.

## FASE 2 — Aplicar al Manual & FAQ (PDF)
1. En `presentaciones/manual-faq-fq-2026-07.html`, la portada (`section.page` #1) ya tiene el
   aire arriba-izquierda reservado. Añade `hero.jpg` como **fondo full-bleed** de esa portada
   con un overlay de gradiente oscuro (izq→der: `#050705` sólido a transparente) para que el
   título/φ sigan legibles sobre el tercio izquierdo. NO metas texto en la imagen; el título es
   el HTML que ya existe.
2. (Opcional) usa `gate.jpg` como banda superior de la pág. 3 ("Cómo funciona / el gate") y
   `social.jpg` como textura tenue de la portada de cierre (pág. 8), siempre con overlay para
   contraste AAA del texto.
3. **Embebe las imágenes como data-URI** (base64) en el HTML para que el PDF sea reproducible
   en cualquier lado. (Para render local también sirve `background:url(assets/hero.jpg)` con
   ruta relativa.)
4. **Re-renderiza el PDF** con Chromium headless (mismo pipeline):
   ```bash
   /opt/pw-browsers/chromium --headless --no-sandbox --disable-gpu --no-pdf-header-footer \
     --print-to-pdf=presentaciones/manual-faq-fq-2026-07.pdf \
     "file://$PWD/presentaciones/manual-faq-fq-2026-07.html"
   ```
   Verifica visualmente (screenshot con `--window-size=794,1123 --screenshot=check.png` y ábrelo).
   `git add -f` el PDF (está en .gitignore pero los decks se commitean).

## FASE 3 — Migrar los decks existentes a la marca nueva
Los `presentaciones/*-2026-06.html` están en la marca VIEJA (crema/esmeralda serif). Migra los
de cara a cliente a la marca LOCK usando el **manual como plantilla** (mismo CSS/tokens/φ):
prioridad **`comparativa-tiers`, `fq-showcase`, `inversionistas`, `estado-producto`**. Añade
`alt.jpg` como portada de cada uno (con overlay). Re-renderiza cada PDF con el comando de la
Fase 2. Conserva el CONTENIDO/números; solo cambia el diseño. Commit por lote.

## FASE 4 — La página / terminal (`cockpit.html`)
1. `cockpit.html` YA está en la marca curada (rain Matrix, φ, oro/Solana) — NO la rehagas.
   Súmale el arte: usa `hero.jpg` o `social.jpg` como **hero/fondo cinematográfico** detrás del
   header, con overlay oscuro para que el texto y la lluvia sigan legibles.
2. **Embébelo como data-URI** (cockpit.html debe ser autocontenido — lo sirve `cockpit_server`
   leyéndolo del disco; nada de hosts externos). Optimiza el peso.
3. ⚠️ `cockpit.html` **SÍ redespliega** el worker (está en `watchPatterns` como excepción). Es
   esperado: el portal se actualiza al hacer merge. No toca la lógica del bot.

---

## Guardrails (no rompas nada)
- **Sin texto en las imágenes de IA.** Títulos/wordmark = texto HTML encima. Si Higgsfield mete
  letras, regenera (no lo enmarques como "espacio para logo").
- **No toques el runtime del bot.** `presentaciones/**`, `internal/**`, `*.pdf`, `*.png` están
  excluidos de `watchPatterns` (no redespliegan). La ÚNICA excepción runtime que tocas es
  `cockpit.html` (y eso es a propósito).
- **Voz measure-first**, sin promesas de dinero, con el disclaimer del manual.
- **No quemes créditos**: `get_cost` antes de cada generación; 2 variaciones máx de la hero.
- **Git**: rama propia de tu sesión, commit por fase, push. (Si aplica el patrón squash-merge
  del repo, realinea con `merge origin/main -X ours` antes del push — mira el historial.)

## Definición de terminado
- `presentaciones/assets/{hero,alt,gate,social}.jpg` generados y optimizados.
- Manual PDF re-renderizado con la portada hero.
- ≥4 decks migrados a la marca nueva y re-renderizados.
- `cockpit.html` con hero cinematográfico, autocontenido, verificado.
- Todo commiteado y pusheado; capturas de verificación revisadas.
