# Conectar la Marketing API de Meta

Objetivo: que, con el video ya renderizado, se pueda **subir y crear la
campana segmentada (con sus variantes y copy) desde codigo** — todo en PAUSA,
para revisar y encender a mano.

> Seguridad: el script (`api/launch.mjs`) es **dry-run por defecto** y, aun con
> `--live`, crea TODO en estado **PAUSED**. No gasta ni publica hasta que tu lo
> enciendas en Ads Manager.

## 1. Requisitos en Meta (una sola vez)

1. **Cuenta de Instagram profesional** (Business/Creator) — ya la tienes.
2. **Pagina de Facebook** vinculada a esa IG (es la identidad del anuncio).
3. **Business Manager** (business.facebook.com) con:
   - tu **cuenta publicitaria** (Ad Account),
   - la Pagina y la cuenta de IG agregadas como activos.
4. **App de Meta** (developers.facebook.com) con el producto **Marketing API**
   agregado.

Para gestionar **tu propia** cuenta publicitaria NO necesitas App Review:
basta un **System User token** con acceso a tus activos.

## 2. Generar el token (System User)

1. Business Manager → **Configuracion del negocio** → **Usuarios → Usuarios del
   sistema** → crea uno (rol Admin).
2. **Agregar activos**: dale acceso a la cuenta publicitaria, la Pagina y la IG.
3. **Generar token** con los permisos:
   `ads_management`, `ads_read`, `business_management`,
   `pages_show_list`, `pages_read_engagement`, `instagram_basic`.
4. Copia el token (de larga duracion).

## 3. Conseguir los IDs

- **Ad Account ID**: Ads Manager → arriba a la izquierda, formato `act_123...`.
  En el `.env` va **sin** el prefijo `act_` (solo los numeros).
- **Page ID**: la Pagina → Configuracion → Informacion, o en Business Manager.
- **IG actor ID**: Business Manager → cuentas de Instagram → ID. (Tambien lo da
  el Graph API Explorer con `me/accounts?fields=instagram_business_account`).

## 4. Configurar `.env`

```bash
cd marketing
cp .env.example .env
# edita .env y pega: META_ACCESS_TOKEN, META_AD_ACCOUNT_ID,
# META_PAGE_ID, META_IG_ACTOR_ID
```

`.env` esta en `.gitignore`: no se sube nunca.

## 5. Probar la conexion (sin crear nada)

```bash
npm run launch        # dry-run: imprime el plan y resuelve la geo (Morelos, etc.)
```

Si ves las `key` de Morelos/Cuernavaca resueltas, el token y la cuenta funcionan.

## 6. Crear la campana (en PAUSA)

```bash
npm run render:all    # asegura que los .mp4 existan en out/
npm run launch:live   # crea campaign + adsets + ads, TODO PAUSED
```

Luego: Ads Manager → revisa creativos, segmentacion (incluye MX, excluye
Morelos/Cuernavaca, placements Reels+Stories) → **enciende** lo que quieras.

## 7. Donde se edita que

- **Segmentacion, presupuesto, placements, destinos** (bot vs Linkme), y el
  **copy** de cada anuncio: `api/campaign.config.json`.
- **Creativos** (los videos): `ads/edl.ts` + `npm run render:all`.

## Notas / limites

- El objetivo por defecto es `OUTCOME_TRAFFIC` con optimizacion a
  `LINK_CLICKS`. El destino de cada conjunto es un link (deep link de Telegram
  `t.me/...?start=ads`, o tu Linkme para el embudo de IG).
- Cripto/finanzas: revisa `META_ADS_PLAYBOOK.md`. Sin promesas de rentabilidad;
  el disclaimer va quemado en el video. Algunas cuentas requieren autorizacion
  previa para anuncios de criptomonedas.
- `instagram_actor_id` puede migrar a `instagram_user_id` en versiones nuevas
  del Graph API; si Meta lo pide, se cambia en `api/meta.mjs`.
