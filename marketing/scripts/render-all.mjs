#!/usr/bin/env node
/**
 * Renderiza TODOS los anuncios del EDL a marketing/out/<id>.mp4.
 * Descubre los ids con `remotion compositions` y renderiza cada uno.
 *
 * Uso: npm run render:all
 */
import {execFileSync} from 'node:child_process';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {mkdirSync} from 'node:fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const ENTRY = 'src/index.ts';
const OUT = path.join(ROOT, 'out');

mkdirSync(OUT, {recursive: true});

const raw = execFileSync('npx', ['remotion', 'compositions', ENTRY, '--quiet'], {
  cwd: ROOT,
  encoding: 'utf8',
});

const ids = raw
  .split('\n')
  .map((l) => l.trim())
  .filter((l) => l && !l.startsWith('showcase-')); // showcase suelto: render aparte si lo quieres

if (ids.length === 0) {
  console.error('No se encontraron composiciones.');
  process.exit(1);
}

for (const id of ids) {
  const out = path.join(OUT, `${id}.mp4`);
  console.log(`\n▶ Render ${id} -> ${path.relative(ROOT, out)}`);
  execFileSync('npx', ['remotion', 'render', ENTRY, id, out], {cwd: ROOT, stdio: 'inherit'});
}

console.log(`\nListo. MP4s en ${path.relative(process.cwd(), OUT)}/`);
