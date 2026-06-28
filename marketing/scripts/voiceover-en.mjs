/**
 * Build the English voiceover tracks for the car ad, perfectly synced to the
 * Remotion scene layout. Each line is synthesized with piper (offline, free)
 * and placed at the exact start time of its scene + a small LEAD so the voice
 * lands as the caption/crossfade settles (not ahead of the subtitles).
 *
 *   node scripts/voiceover-en.mjs
 *
 * Outputs (loudness-normalized, full ad length, car-engine ambience folded in):
 *   public/audio/vo-en-g1.wav      → Telegram CTA ("text me FQ")
 *   public/audio/vo-en-g1-web.wav  → landing CTA ("get the free guide below")
 */
import {execFileSync} from 'node:child_process';
import {mkdirSync, rmSync} from 'node:fs';
import {createRequire} from 'node:module';

const require = createRequire(import.meta.url);
const ffmpeg = require('ffmpeg-static');
const VOICE = `${process.cwd()}/tts/voices/en_US-ryan-high.onnx`;
const PARTS = `${process.cwd()}/tts/parts`;
const CAR = `${process.cwd()}/public/audio/IMG_1835.wav`;
const CAR_SS = 3.0;
const CAR_LEN = 3.6;

// Lead-in: captions fade in over ~8 frames and the scenes crossfade by 8 frames,
// so the voice must arrive ~0.37s AFTER the raw scene start to feel in time.
const LEAD = 367; // ms

// Shared lines + the scene start time (ms). The 6th line (CTA) is per-variant.
const COMMON = [
  {t: 'Why will most people never drive one of these? It is not luck. And it is not the market.', delay: 733, ls: 1.0},
  {t: 'The market did not rob you. You robbed yourself. No system, pure emotion.', delay: 7667, ls: 1.0},
  {t: 'They buy on a feeling. They sell on fear.', delay: 12200, ls: 1.0},
  {t: 'The day you lean on a system instead of your ego, a bot, like Fibonacci Quantum, everything changes.', delay: 15533, ls: 1.02},
  {t: 'It hands you the trade ready. Entry, stop, target. Zero emotion.', delay: 21833, ls: 1.0},
];
const CTA_LINE = {
  telegram: {t: 'I do not sell a dream. I show the wins and the losses. Text me F Q on Telegram.', delay: 26567, ls: 1.0},
  web: {t: 'I do not sell a dream. I show the wins and the losses. Get the free guide below.', delay: 26567, ls: 1.0},
};
const TOTAL_MS = 31567;
const CAR_DELAY = 733 + LEAD; // engine bed lands with the car shot

rmSync(PARTS, {recursive: true, force: true});
mkdirSync(PARTS, {recursive: true});

const synth = (text, ls, file) =>
  execFileSync('piper', ['-m', VOICE, '--length_scale', String(ls), '-f', file], {input: text});

const buildStem = (lines, out) => {
  lines.forEach((l, i) => {
    l.file = `${PARTS}/${out.replace(/[^a-z0-9]/gi, '_')}_${i}.wav`;
    synth(l.t, l.ls, l.file);
  });

  const inputs = [...lines.flatMap((l) => ['-i', l.file]), '-ss', String(CAR_SS), '-t', String(CAR_LEN), '-i', CAR];
  const carIdx = lines.length;
  const voDelays = lines.map((l, i) => `[${i}:a]adelay=${l.delay + LEAD}|${l.delay + LEAD}[d${i}]`).join(';');
  const voMixIn = lines.map((_, i) => `[d${i}]`).join('');
  const carChain =
    `[${carIdx}:a]highpass=f=70,lowpass=f=5200,afade=t=in:st=0:d=0.4,afade=t=out:st=${CAR_LEN - 0.7}:d=0.7,` +
    `volume=0.42,adelay=${CAR_DELAY}|${CAR_DELAY}[car]`;
  const filter =
    `${voDelays};${voMixIn}amix=inputs=${lines.length}:normalize=0:dropout_transition=0[vo];` +
    `${carChain};` +
    `[vo]highpass=f=90,equalizer=f=3200:t=q:w=1.6:g=2.5,` +
    `acompressor=threshold=-18dB:ratio=3:attack=8:release=160[vom];` +
    `[vom][car]amix=inputs=2:normalize=0:dropout_transition=0[mx];` +
    `[mx]apad,atrim=0:${(TOTAL_MS / 1000).toFixed(3)},alimiter=limit=0.92,loudnorm=I=-15:TP=-1.5:LRA=11[out]`;
  execFileSync(ffmpeg, ['-y', ...inputs, '-filter_complex', filter, '-map', '[out]', '-ar', '48000', '-ac', '1', out],
    {stdio: 'inherit'});
  process.stdout.write(`\nVO written: ${out}\n`);
};

buildStem([...COMMON, CTA_LINE.telegram], `${process.cwd()}/public/audio/vo-en-g1.wav`);
buildStem([...COMMON, CTA_LINE.web], `${process.cwd()}/public/audio/vo-en-g1-web.wav`);
