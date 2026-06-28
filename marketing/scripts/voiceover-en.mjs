/**
 * Build the English voiceover track for the car ad (g1-en), perfectly synced
 * to the Remotion scene layout. Each line is synthesized with piper (offline,
 * free) and placed at the exact start time of its scene (frame offsets account
 * for the 8-frame crossfades, same math as AdMovie's `starts[]`).
 *
 *   node scripts/voiceover-en.mjs
 *
 * Output: public/audio/vo-en-g1.wav  (loudness-normalized, full ad length)
 */
import {execFileSync} from 'node:child_process';
import {mkdirSync, rmSync} from 'node:fs';
import {createRequire} from 'node:module';

const require = createRequire(import.meta.url);
const ffmpeg = require('ffmpeg-static');
const VOICE = `${process.cwd()}/tts/voices/en_US-ryan-high.onnx`;
const PARTS = `${process.cwd()}/tts/parts`;
const OUT = `${process.cwd()}/public/audio/vo-en-g1.wav`;
// Car engine/ambience rescued from the car B-roll (IMG_1835), synced to the
// on-screen car shot (overlay inSec 3). Sits low under the VO during the hook.
const CAR = `${process.cwd()}/public/audio/IMG_1835.wav`;
const CAR_SS = 3.0; // start in the source (matches the overlay)
const CAR_LEN = 3.6; // covers the car shot + a touch of tail
const CAR_DELAY = 800; // ms — lands just as the hook/car shot comes in

rmSync(PARTS, {recursive: true, force: true});
mkdirSync(PARTS, {recursive: true});

// Lines + start time (ms) of the scene they sit on. length_scale < 1 = faster.
// Windows (next start - this start): hook 6.93s, b1 4.5s, b2 3.3s, b3 6.3s,
// showcase 4.7s, cta 5.0s. Lines written to fit; a slight bridge is fine.
const LINES = [
  {t: 'Why will most people never drive one of these? It is not luck. And it is not the market.', delay: 733, ls: 1.0},
  {t: 'The market did not rob you. You robbed yourself. No system, pure emotion.', delay: 7667, ls: 1.0},
  {t: 'They buy on a feeling. They sell on fear.', delay: 12200, ls: 1.0},
  {t: 'The day you lean on a system instead of your ego, a bot, like Fibonacci Quantum, everything changes.', delay: 15533, ls: 1.02},
  {t: 'It hands you the trade ready. Entry, stop, target. Zero emotion.', delay: 21833, ls: 1.0},
  {t: 'I do not sell a dream. I show the wins and the losses. Text me F Q on Telegram.', delay: 26567, ls: 1.0},
];
const TOTAL_MS = 31567;

LINES.forEach((l, i) => {
  const f = `${PARTS}/line${i}.wav`;
  execFileSync('piper', ['-m', VOICE, '--length_scale', String(l.ls), '-f', f], {input: l.t});
  l.file = f;
  process.stdout.write(`  synth line ${i}\n`);
});

// Inputs: the 6 VO lines + the car ambience clip (last input).
const inputs = [...LINES.flatMap((l) => ['-i', l.file]), '-ss', String(CAR_SS), '-t', String(CAR_LEN), '-i', CAR];
const carIdx = LINES.length;

// VO chain: each line delayed to its scene, mixed, lightly mastered. The VO is
// the lead — clean, present, the bed never fights it.
const voDelays = LINES.map((l, i) => `[${i}:a]adelay=${l.delay}|${l.delay}[d${i}]`).join(';');
const voMixIn = LINES.map((_, i) => `[d${i}]`).join('');

// Car bed: tame the harshness, fade in/out, keep it low, delay to the car shot.
const carChain =
  `[${carIdx}:a]highpass=f=70,lowpass=f=5200,afade=t=in:st=0:d=0.4,afade=t=out:st=${CAR_LEN - 0.7}:d=0.7,` +
  `volume=0.42,adelay=${CAR_DELAY}|${CAR_DELAY}[car]`;

const filter =
  `${voDelays};${voMixIn}amix=inputs=${LINES.length}:normalize=0:dropout_transition=0[vo];` +
  `${carChain};` +
  // VO mastering before the merge so the engine reads as ambience, not as VO.
  `[vo]highpass=f=90,equalizer=f=3200:t=q:w=1.6:g=2.5,` +
  `acompressor=threshold=-18dB:ratio=3:attack=8:release=160[vom];` +
  // Merge VO (lead) + car bed, then final true-peak-safe loudness pass.
  `[vom][car]amix=inputs=2:normalize=0:dropout_transition=0[mx];` +
  `[mx]apad,atrim=0:${(TOTAL_MS / 1000).toFixed(3)},` +
  `alimiter=limit=0.92,loudnorm=I=-15:TP=-1.5:LRA=11[out]`;

execFileSync(ffmpeg, ['-y', ...inputs, '-filter_complex', filter, '-map', '[out]', '-ar', '48000', '-ac', '1', OUT],
  {stdio: 'inherit'});
process.stdout.write(`\nVO written: ${OUT}\n`);
