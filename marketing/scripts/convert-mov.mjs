/**
 * Convierte todo .MOV/.mov en public/footage/ a .mp4 (H.264 + AAC, faststart).
 * REQUERIDO antes de `npm run render:all`: el loader (src/components/ClipSegment.tsx)
 * pide `footage/<src>.mp4`, pero los reels fuente de Drive vienen en .MOV.
 * Uso: npm run convert   (luego `npm run render:all`).
 */
import {readdirSync, existsSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {join, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';

const FOOTAGE = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'footage');
let ffmpeg = 'ffmpeg';
try { const m = await import('ffmpeg-static'); ffmpeg = m.default || 'ffmpeg'; } catch {}

if (!existsSync(FOOTAGE)) { console.error('No existe la carpeta', FOOTAGE); process.exit(1); }
const movs = readdirSync(FOOTAGE).filter((f) => /\.mov$/i.test(f));
if (!movs.length) { console.log('Sin .MOV que convertir en', FOOTAGE); process.exit(0); }
for (const f of movs) {
  const out = f.replace(/\.mov$/i, '.mp4');
  console.log(`→ ${f}  →  ${out}`);
  execFileSync(ffmpeg, ['-y', '-i', join(FOOTAGE, f), '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
    '-crf', '20', '-c:a', 'aac', '-movflags', '+faststart', join(FOOTAGE, out)], {stdio: 'inherit'});
}
console.log(`Listo: ${movs.length} .MOV → .mp4 en ${FOOTAGE}`);
