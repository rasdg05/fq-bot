/**
 * Cliente minimo de la Marketing API de Meta (Graph API).
 * Sin SDK pesado: usa fetch nativo de Node 22. Carga .env a mano.
 *
 * Expone helpers para: resolver geo por nombre, subir video, esperar
 * procesamiento, y crear campaign / adset / creative / ad.
 *
 * Todo lo que crea va en estado PAUSED (ver launch.mjs). Nada gasta hasta
 * que lo enciendas en Ads Manager.
 */
import {readFileSync, existsSync, openAsBlob} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ENV_PATH = path.resolve(__dirname, '..', '.env');

// Carga .env simple (KEY=VALUE), sin sobreescribir lo ya presente.
if (existsSync(ENV_PATH)) {
  for (const line of readFileSync(ENV_PATH, 'utf8').split('\n')) {
    const m = /^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/.exec(line);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, '');
  }
}

export const CFG = {
  token: process.env.META_ACCESS_TOKEN || '',
  adAccount: (process.env.META_AD_ACCOUNT_ID || '').replace(/^act_/, ''),
  pageId: process.env.META_PAGE_ID || '',
  igActor: process.env.META_IG_ACTOR_ID || '',
  version: process.env.META_GRAPH_VERSION || 'v21.0',
};

const BASE = () => `https://graph.facebook.com/${CFG.version}`;

export function assertCreds() {
  const missing = ['token', 'adAccount', 'pageId', 'igActor'].filter((k) => !CFG[k]);
  if (missing.length) {
    throw new Error(
      `Faltan credenciales en .env: ${missing.join(', ')}. Ver docs/META_API_SETUP.md`
    );
  }
}

async function call(method, edge, params = {}, isMultipart = false, form = null) {
  const url = new URL(`${BASE()}/${edge}`);
  let opts = {method};
  if (isMultipart) {
    form.set('access_token', CFG.token);
    opts.body = form;
  } else if (method === 'GET') {
    for (const [k, v] of Object.entries(params)) {
      url.searchParams.set(k, typeof v === 'object' ? JSON.stringify(v) : v);
    }
    url.searchParams.set('access_token', CFG.token);
  } else {
    const body = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      body.set(k, typeof v === 'object' ? JSON.stringify(v) : v);
    }
    body.set('access_token', CFG.token);
    opts.body = body;
  }
  const res = await fetch(url, opts);
  const json = await res.json();
  if (!res.ok || json.error) {
    throw new Error(`Meta API ${edge}: ${JSON.stringify(json.error || json)}`);
  }
  return json;
}

/** Resuelve una geolocalizacion por nombre (region/ciudad/pais). */
export async function searchGeo(q, locationType = 'region') {
  const r = await call('GET', 'search', {
    type: 'adgeolocation',
    location_types: [locationType],
    q,
    limit: 5,
  });
  return r.data || [];
}

/** Sube un video y devuelve su id. */
export async function uploadVideo(filePath, name) {
  const blob = await openAsBlob(filePath);
  const form = new FormData();
  form.set('source', blob, path.basename(filePath));
  if (name) form.set('name', name);
  const r = await call('POST', `act_${CFG.adAccount}/advideos`, {}, true, form);
  return r.id;
}

/** Espera a que el video termine de procesarse. */
export async function waitVideoReady(videoId, timeoutMs = 180000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const r = await call('GET', videoId, {fields: 'status'});
    const phase = r.status?.video_status || r.status?.processing_progress;
    if (r.status?.video_status === 'ready') return true;
    if (r.status?.video_status === 'error') throw new Error(`Video ${videoId} fallo al procesar`);
    await new Promise((res) => setTimeout(res, 4000));
  }
  throw new Error(`Timeout esperando el video ${videoId}`);
}

/** Primer thumbnail (uri) del video, para usar como portada del creativo. */
export async function videoThumbnail(videoId) {
  const r = await call('GET', `${videoId}/thumbnails`, {fields: 'uri,is_preferred'});
  const pref = (r.data || []).find((t) => t.is_preferred) || (r.data || [])[0];
  return pref?.uri;
}

export async function createCampaign(name, objective) {
  const r = await call('POST', `act_${CFG.adAccount}/campaigns`, {
    name,
    objective, // p.ej. OUTCOME_TRAFFIC
    status: 'PAUSED',
    special_ad_categories: [],
  });
  return r.id;
}

export async function createAdSet(campaignId, spec) {
  const r = await call('POST', `act_${CFG.adAccount}/adsets`, {
    campaign_id: campaignId,
    status: 'PAUSED',
    ...spec,
  });
  return r.id;
}

export async function createCreative(name, spec) {
  const r = await call('POST', `act_${CFG.adAccount}/adcreatives`, {name, ...spec});
  return r.id;
}

export async function createAd(name, adsetId, creativeId) {
  const r = await call('POST', `act_${CFG.adAccount}/ads`, {
    name,
    adset_id: adsetId,
    creative: {creative_id: creativeId},
    status: 'PAUSED',
  });
  return r.id;
}
