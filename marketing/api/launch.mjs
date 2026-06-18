#!/usr/bin/env node
/**
 * Lanza (o simula) una campana en Meta a partir de api/campaign.config.json.
 *
 *   node api/launch.mjs            # DRY-RUN: imprime el plan, no crea nada.
 *   node api/launch.mjs --live     # Crea campaign/adsets/ads en estado PAUSED.
 *
 * SEGURIDAD:
 *  - Dry-run por defecto. Nunca crea nada sin --live.
 *  - Aun con --live, TODO se crea PAUSED: no gasta ni sale al aire hasta que
 *    lo enciendas a mano en Ads Manager tras revisarlo.
 */
import {readFileSync, existsSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import * as Meta from './meta.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const LIVE = process.argv.includes('--live');

const cfg = JSON.parse(readFileSync(path.join(__dirname, 'campaign.config.json'), 'utf8'));

const log = (...a) => console.log(...a);
const head = (t) => log(`\n── ${t}`);

async function resolveGeo() {
  const targeting = {
    geo_locations: {countries: cfg.geo.includeCountries},
    excluded_geo_locations: {},
    publisher_platforms: ['instagram', 'facebook'],
    instagram_positions: cfg.placements.instagramPositions,
    facebook_positions: cfg.placements.facebookPositions,
  };

  if (cfg.geo.excludeRegions?.length) {
    const regions = [];
    for (const name of cfg.geo.excludeRegions) {
      const hits = (await Meta.searchGeo(name, 'region')).filter((h) => h.country_code === 'MX');
      if (!hits.length) throw new Error(`No se resolvio la region: ${name}`);
      log(`   region excluida: ${hits[0].name} (key ${hits[0].key})`);
      regions.push({key: hits[0].key});
    }
    targeting.excluded_geo_locations.regions = regions;
  }

  if (cfg.geo.excludeCities?.length) {
    const cities = [];
    for (const c of cfg.geo.excludeCities) {
      const hits = (await Meta.searchGeo(c.name, 'city')).filter((h) => h.country_code === 'MX');
      if (!hits.length) throw new Error(`No se resolvio la ciudad: ${c.name}`);
      log(`   ciudad excluida: ${hits[0].name} (key ${hits[0].key}, r=${c.radiusKm}km)`);
      cities.push({key: hits[0].key, radius: c.radiusKm, distance_unit: 'kilometer'});
    }
    targeting.excluded_geo_locations.cities = cities;
  }

  return targeting;
}

async function main() {
  head('Plan de campana');
  log(`   Nombre:     ${cfg.campaignName}`);
  log(`   Objetivo:   ${cfg.objective}`);
  log(`   Presupuesto:${cfg.dailyBudgetMXN} MXN/dia por conjunto`);
  log(`   Incluye:    ${cfg.geo.includeCountries.join(', ')}`);
  log(`   Excluye:    ${cfg.geo.excludeRegions?.join(', ') || '-'} / ${(cfg.geo.excludeCities || []).map((c) => c.name).join(', ') || '-'}`);
  log(`   Placements: IG[${cfg.placements.instagramPositions.join(',')}] FB[${cfg.placements.facebookPositions.join(',')}]`);
  log(`   Anuncios:   ${cfg.ads.length} (${cfg.adSets.length} conjuntos)`);

  // Verifica que los videos existan.
  const missing = cfg.ads.filter((a) => !existsSync(path.join(ROOT, a.video)));
  if (missing.length) {
    log(`\n⚠ Faltan videos renderizados:`);
    for (const a of missing) log(`   - ${a.video}  (corre: npm run render:all)`);
  }

  if (!LIVE) {
    head('DRY-RUN');
    log('   No se crea nada. Para crear (en PAUSA) corre: node api/launch.mjs --live');
    if (Meta.CFG.token) {
      try {
        head('Test de conexion (resolviendo geo)');
        await resolveGeo();
        log('   Conexion OK.');
      } catch (e) {
        log(`   Geo/conexion fallo: ${e.message}`);
      }
    } else {
      log('\n   (Sin META_ACCESS_TOKEN: no pruebo conexion. Ver docs/META_API_SETUP.md)');
    }
    return;
  }

  // --- LIVE ---
  Meta.assertCreds();
  if (missing.length) throw new Error('Renderiza los videos faltantes antes de --live.');

  head('Resolviendo segmentacion');
  const targeting = await resolveGeo();

  head('Creando campana (PAUSED)');
  const campaignId = await Meta.createCampaign(cfg.campaignName, cfg.objective);
  log(`   campaign ${campaignId}`);

  const adSetIds = {};
  for (const as of cfg.adSets) {
    const id = await Meta.createAdSet(campaignId, {
      name: as.name,
      daily_budget: Math.round(cfg.dailyBudgetMXN * 100), // centavos
      billing_event: 'IMPRESSIONS',
      optimization_goal: 'LINK_CLICKS',
      destination_type: 'WEBSITE',
      targeting,
    });
    adSetIds[as.key] = {id, link: as.link, cta: as.cta};
    log(`   adset ${as.key} -> ${id}`);
  }

  head('Subiendo videos y creando anuncios (PAUSED)');
  for (const ad of cfg.ads) {
    const as = adSetIds[ad.adSet];
    if (!as) throw new Error(`Ad ${ad.id} apunta a un adSet inexistente: ${ad.adSet}`);
    log(`   ${ad.id}: subiendo video...`);
    const videoId = await Meta.uploadVideo(path.join(ROOT, ad.video), ad.id);
    await Meta.waitVideoReady(videoId);
    const thumb = await Meta.videoThumbnail(videoId);

    const creativeId = await Meta.createCreative(`creative-${ad.id}`, {
      object_story_spec: {
        page_id: Meta.CFG.pageId,
        instagram_actor_id: Meta.CFG.igActor,
        video_data: {
          video_id: videoId,
          image_url: thumb,
          message: ad.primaryText,
          title: ad.headline,
          link_description: ad.description,
          call_to_action: {type: as.cta, value: {link: as.link}},
        },
      },
    });
    const adId = await Meta.createAd(`ad-${ad.id}`, as.id, creativeId);
    log(`   ${ad.id}: ad ${adId} (PAUSED)`);
  }

  head('Listo');
  log('   Todo creado en PAUSA. Revisa en Ads Manager y enciende cuando quieras.');
}

main().catch((e) => {
  console.error(`\nError: ${e.message}`);
  process.exit(1);
});
