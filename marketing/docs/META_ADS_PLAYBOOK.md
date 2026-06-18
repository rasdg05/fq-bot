# Playbook de Meta Ads — FQ

Guia operativa para lanzar campanas que dirijan al **bot de Telegram** y/o al
**perfil de Instagram**, controlando donde se muestran y sin que aparezcan
como post organico en tu feed.

> Las pantallas de Meta cambian de nombre seguido. Los conceptos (no los
> textos exactos del boton) son lo que importa.

---

## 1. Que tus anuncios NO aparezcan en tu feed/perfil

Esto es lo que mas confunde. Los anuncios **no se publican** en tu feed por
defecto. La clave es **como** los creas:

- **Crea el anuncio en Ads Manager** (Administrador de anuncios), **no** con el
  boton "Promocionar"/"Boost" de la app. Boost convierte un post existente del
  feed en anuncio; eso si queda visible en tu perfil.
- Al crear el anuncio elige **"Crear anuncio"** (subir el video nuevo), **no**
  "Usar publicacion existente". Asi el anuncio queda como *publicacion no
  publicada* ("dark post"): se muestra solo a tu audiencia objetivo y **no
  aparece** en la cuadricula de tu perfil ni en tu feed.
- Si necesitas reutilizar el mismo post entre anuncios, usalo desde
  **"Publicaciones existentes" → "Anuncios"** (no las publicadas), que viven
  fuera del feed.

Resultado: tus seguidores no ven el anuncio en tu perfil; solo lo ve la
audiencia que segmentes en los placements elegidos.

---

## 2. Delimitar DONDE se muestran (placements)

En el nivel **Conjunto de anuncios** → **Ubicaciones**:

- Cambia de **"Ubicaciones Advantage+"** (automaticas) a **"Ubicaciones
  manuales"**. Esto es lo que te da el control fino.
- Selecciona/deselecciona por superficie:
  - **Reels** (IG + FB) y **Stories** → recomendado para 9:16.
  - **Feeds** (Facebook Feed, Instagram Feed, Explorar) → activalo o quitalo
    segun quieras o no aparecer en feeds.
  - **In-stream, Search, Messages, Audience Network** → normalmente fuera para
    creatividades verticales de marca.
- Regla practica para FQ: **Reels + Stories** activos, resto segun pruebas. Asi
  el formato 9:16 se ve nativo y delimitas la superficie.

---

## 3. Delimitar la ZONA geografica

En **Conjunto de anuncios** → **Audiencia** → **Ubicaciones**:

- **Incluir** paises / regiones / ciudades, o **pin + radio** (radio ~1–80 km
  alrededor de un punto).
- **Excluir** zonas: usa "Excluir" para sacar areas concretas (p.ej. tu ciudad
  si no quieres mostrarte localmente, o regiones de bajo valor).
- Cuida el selector **"Personas que viven aqui"** vs "que estuvieron
  recientemente": para suscripciones usa **residentes**.
- Idioma: si tu creativo es en espanol, fija **Idioma = Espanol** para no pagar
  impresiones fuera de tu mercado.

### Receta: excluir Cuernavaca / Morelos (hometown)
1. **Incluir**: Mexico (o las regiones que vendas).
2. **Excluir** (campo "Excluir"): agrega el **estado de Morelos**. Asi sacas todo
   el estado, no solo la ciudad.
3. Opcional mas estricto: ademas de la region, excluye **Cuernavaca** como
   ciudad, o un **pin + radio** (~17–25 km) centrado en Cuernavaca.
4. Selector: **"Personas que viven en este lugar"** (no "recientemente"), para
   que la exclusion siga a residentes locales.
5. Salvedad: alguien de Morelos de viaje dentro de tu zona incluida podria verlo;
   y no filtra conocidos que vivan fuera del estado. Pero combinado con el
   *dark post* (no sale en tu feed) quedas bien cubierto frente a tu hometown.

> En la API esto es `excluded_geo_locations` con la `region key` de Morelos
> (el script la resuelve por nombre via Targeting Search, no se hardcodea).

---

## 4. Cripto / productos financieros (LEER antes de lanzar)

Meta restringe la publicidad de productos y servicios financieros y de
criptomonedas. Para no caer en rechazos o bloqueos:

- **Prohibido**: prometer rentabilidad, "duplica tu dinero", P&L, testimonios
  de ganancias, "señales infalibles", urgencia tipo "hazte rico".
- **Permitido / recomendado**: lenguaje educativo y de proceso (disciplina,
  estructura, gestion de riesgo), con **aviso de riesgo visible**. El microtexto
  legal de las creatividades ya cumple esto: *"Rendimientos pasados no
  garantizan resultados futuros. No es asesoria financiera."*
- Algunas categorias de cripto exigen **autorizacion previa** de Meta. Si la
  cuenta lo pide, completa el formulario de permiso para anunciantes de
  criptomonedas antes de escalar presupuesto.
- La **landing** (bot o perfil) debe ser coherente con el anuncio y mostrar el
  disclaimer (tu `legal.py` ya lo cubre en el bot).

---

## 5. CTA: bot de Telegram vs Instagram

No se puede usar el objetivo "Mensajes" para Telegram (eso es Messenger/
WhatsApp/IG). Para cada destino:

### Bot de Telegram
- Objetivo: **Trafico** (o **Interacciones**) con destino **Sitio web**.
- URL: el deep link del bot con parametro de campana, p.ej.
  `https://t.me/TU_BOT?start=ads` (asi atribuyes la fuente dentro del bot).
- CTA del boton: "Mas informacion" / "Registrarte".

### Perfil de Instagram → Linkme (hub link-in-bio)
- Objetivo: **Trafico** a tu perfil, o **Interacciones → visitas al perfil**.
- Asegura que el anuncio corra desde la **cuenta de IG** correcta (identidad
  del anuncio).
- CTA: "Seguir" no existe como boton de anuncio; usa "Mas informacion" llevando
  al perfil, y que el video pida seguir.
- **El embudo real**: anuncio → perfil de IG → en la **bio** tienes tu link de
  **Linkme** → desde ahi la gente entra a tu **canal**, te **sigue en IG**, va a
  **YouTube**, etc. Por eso el CTA de las creatividades IG dice
  *"link en bio · linkme..."* (configurado en `tokens.ts → CTA_CONFIG.linkme`).
- Acciones: pon el link de Linkme **fijo en la bio** antes de lanzar, y etiqueta
  con UTMs por canal dentro de Linkme para medir a donde va el trafico.

> Recomendado: separar en **dos conjuntos de anuncios** (uno → bot, otro →
> perfil/Linkme) para medir cual convierte mejor, en vez de mezclar destinos.

---

## 7. Como encontrar el anuncio GANADOR

No paramos hasta tener un ganador. Metodo:

1. **Fija todo menos el hook.** Mismo cuerpo, mismo CTA; cambia solo los
   primeros 3s. El EDL ya trae variantes (`a1b`, `a2b`) justo para esto.
2. **Una campana, varios anuncios** (ABO o Advantage+ con varias creatividades).
   Arranca 3–5 hooks por destino.
3. **Metrica de filtro temprano:** hook rate (3s/thruplays) y CTR. Mata lo que
   no engancha en 24–48h con presupuesto bajo.
4. **Metrica de decision:** costo por click al bot / por visita de perfil, y
   luego suscripciones (atribuidas con `?start=ads` en el bot y UTMs en Linkme).
5. **Escala** el hook ganador, genera 2–3 variantes nuevas alrededor de el, y
   repite. El ganador casi siempre es cuestion de hook, no del cuerpo.

---

## 6. Checklist de lanzamiento

- [ ] Video 9:16, < 30s, subtitulos quemados, disclaimer visible.
- [ ] Creado en Ads Manager como anuncio nuevo (no Boost, no post publicado).
- [ ] Ubicaciones manuales: Reels + Stories (ajustar Feed a gusto).
- [ ] Geo incluida/excluida + idioma Espanol + residentes.
- [ ] Sin promesas de rentabilidad. Aviso de riesgo presente.
- [ ] Deep link `t.me/...?start=ads` o destino de perfil correcto.
- [ ] Bot/perfil con disclaimer coherente.
- [ ] Conjuntos separados por destino (bot vs IG) para medir.
```
