#!/usr/bin/env node
/**
 * Ingesta de footage para FQ.
 *
 * Para cada .mp4 en marketing/public/footage/:
 *   1. Mide la duracion.
 *   2. Genera un "contact sheet" (mosaico 5x5 de fotogramas) en
 *      marketing/public/contact-sheets/<name>.jpg  -> lo subes al chat y
 *      con eso elegimos los mejores segundos para el EDL.
 *   3. (Opcional --proxy) transcodifica un proxy H.264 yuv420p, el formato
 *      que mejor lee OffthreadVideo de Remotion.
 *
 * Uso:
 *   npm run ingest            # contact sheets
 *   npm run ingest -- --proxy # ademas genera proxies normalizados
 *
 * Requiere ffmpeg-static (se instala con npm install). No usa apt.
 */
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {readdir, mkdir, stat} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import ffmpegStatic from 'ffmpeg-static';

const exec = promisify(execFile);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const FOOTAGE = path.join(ROOT, 'public', 'footage');
const SHEETS = path.join(ROOT, 'public', 'contact-sheets');
const PROXIES = path.join(ROOT, 'public', 'proxies');

const wantProxy = process.argv.includes('--proxy');

/** Duracion en segundos parseando el stderr de ffmpeg. */
async function duration(file) {
  try {
    await exec(ffmpegStatic, ['-i', file]);
  } catch (e) {
    const m = /Duration:\s*(\d+):(\d+):(\d+\.\d+)/.exec(e.stderr || '');
    if (m) return (+m[1]) * 3600 + (+m[2]) * 60 + parseFloat(m[3]);
  }
  return 0;
}

async function contactSheet(file, name, dur) {
  const out = path.join(SHEETS, `${name}.jpg`);
  // 25 fotogramas distribuidos en toda la duracion, mosaico 5x5.
  const n = 25;
  const fps = dur > 0 ? n / dur : 1;
  await exec(ffmpegStatic, [
    '-y', '-i', file,
    '-vf', `fps=${fps.toFixed(4)},scale=320:-1,tile=5x5`,
    '-frames:v', '1',
    out,
  ]);
  return out;
}

async function proxy(file, name) {
  const out = path.join(PROXIES, `${name}.mp4`);
  await exec(ffmpegStatic, [
    '-y', '-i', file,
    '-vf', 'scale=1080:-2:force_original_aspect_ratio=decrease',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-preset', 'veryfast', '-crf', '23',
    '-c:a', 'aac', '-movflags', '+faststart',
    out,
  ]);
  return out;
}

async function main() {
  if (!ffmpegStatic) {
    console.error('ffmpeg-static no disponible. Corre `npm install` primero.');
    process.exit(1);
  }
  if (!existsSync(FOOTAGE)) {
    await mkdir(FOOTAGE, {recursive: true});
    console.log(`Carpeta creada: ${FOOTAGE}`);
    console.log('Copia ahi tus .mp4 (mismo nombre que en ads/edl.ts) y vuelve a correr.');
    return;
  }
  await mkdir(SHEETS, {recursive: true});
  if (wantProxy) await mkdir(PROXIES, {recursive: true});

  const files = (await readdir(FOOTAGE)).filter((f) => f.toLowerCase().endsWith('.mp4'));
  if (files.length === 0) {
    console.log(`Sin .mp4 en ${FOOTAGE}. Copia tus clips ahi.`);
    return;
  }

  for (const f of files) {
    const name = f.replace(/\.mp4$/i, '');
    const file = path.join(FOOTAGE, f);
    const {size} = await stat(file);
    const dur = await duration(file);
    process.stdout.write(`• ${name}  ${(size / 1e6).toFixed(0)}MB  ${dur.toFixed(1)}s ... `);
    const sheet = await contactSheet(file, name, dur);
    if (wantProxy) await proxy(file, name);
    console.log(`hoja: ${path.relative(ROOT, sheet)}${wantProxy ? ' (+proxy)' : ''}`);
  }

  console.log('\nListo. Sube las imagenes de public/contact-sheets/ al chat');
  console.log('para que marquemos los mejores segundos en ads/edl.ts.');
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
