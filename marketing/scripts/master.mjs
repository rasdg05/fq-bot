#!/usr/bin/env node
/**
 * Masterizado de audio para los anuncios (la gente compra con el oido).
 * Toma out/<id>.mp4 y produce out/<id>-master.mp4 con:
 *   - highpass 80 Hz   -> quita retumbe/viento
 *   - +1.5 dB ~120 Hz  -> calidez/cuerpo (emocion del motor)
 *   - +2.5 dB ~3 kHz   -> presencia e inteligibilidad de la voz
 *   - compresor suave  -> nivela picos, voz constante
 *   - loudnorm -14 LUFS-> volumen parejo, estandar IG/Reels
 * El video se copia tal cual (sin re-encodear -> sin perdida).
 *
 * Uso:  node scripts/master.mjs g1-auto-cover
 *       node scripts/master.mjs            (procesa todos los out/*.mp4 sin -master)
 */
import {execFileSync} from 'node:child_process';
import {readdirSync, existsSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import ffmpeg from 'ffmpeg-static';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(__dirname, '..', 'out');

const AF = [
  'highpass=f=85', // quita retumbe
  'equalizer=f=300:t=q:w=1.2:g=-2', // limpia barro/lodo -> mas nitido
  'equalizer=f=120:t=q:w=1.0:g=1.5', // calidez/cuerpo
  'equalizer=f=3500:t=q:w=1.3:g=3', // presencia de voz
  'treble=g=3:f=9000', // aire/brillo (nitidez)
  'aexciter=amount=2:blend=2:freq=7500', // armonicos -> mas auditivo e interesante
  'acompressor=threshold=-18dB:ratio=3:attack=15:release=180', // nivela
  'alimiter=limit=0.95', // controla picos
  'loudnorm=I=-13:TP=-1:LRA=10', // volumen parejo y fuerte
].join(',');

function master(id) {
  const input = path.join(OUT, `${id}.mp4`);
  const output = path.join(OUT, `${id}-master.mp4`);
  if (!existsSync(input)) {
    console.error(`No existe: ${input}`);
    return;
  }
  console.log(`Masterizando ${id} ...`);
  execFileSync(
    ffmpeg,
    ['-y', '-i', input, '-c:v', 'copy', '-af', AF, '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', output],
    {stdio: 'inherit'}
  );
  console.log(`  -> out/${id}-master.mp4`);
}

const arg = process.argv[2];
if (arg) {
  master(arg.replace(/\.mp4$/, ''));
} else {
  const ids = readdirSync(OUT)
    .filter((f) => f.endsWith('.mp4') && !f.includes('-master') && !f.includes('-LIGHT'))
    .map((f) => f.replace(/\.mp4$/, ''));
  for (const id of ids) master(id);
}
