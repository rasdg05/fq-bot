/**
 * Build the COMPLETE English audio master for the car ad — one self-contained
 * stem (voice + ducked music + car ambience), perfectly synced to the Remotion
 * scene layout. Remotion just plays this stem (its own music layer is disabled
 * in voiceover mode), so the mix is fully controlled here.
 *
 *   node scripts/voiceover-en.mjs
 *
 * No dead air: the music sits up and energetic in the gaps between lines and
 * sidechain-ducks under the voice when speaking (radio/podcast standard), so the
 * energy never drops. Piper (offline) for the voice; ffmpeg for the mix.
 *
 * Outputs:
 *   public/audio/vo-en-g1.wav      → Telegram CTA
 *   public/audio/vo-en-g1-web.wav  → landing CTA
 */
import {execFileSync} from 'node:child_process';
import {mkdirSync, rmSync} from 'node:fs';
import {createRequire} from 'node:module';

const require = createRequire(import.meta.url);
const ffmpeg = require('ffmpeg-static');
const VOICE = `${process.cwd()}/tts/voices/en_US-ryan-high.onnx`;
const PARTS = `${process.cwd()}/tts/parts`;
const MUSIC = `${process.cwd()}/public/audio/music.mp3`;
const CAR = `${process.cwd()}/public/audio/IMG_1835.wav`;
const CAR_SS = 3.0;
const CAR_LEN = 3.6;

// Lead-in so the voice lands with the caption/crossfade (not ahead of the subs).
const LEAD = 367; // ms
const TOTAL = 31.567; // s
const CAR_DELAY = 733 + LEAD;

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

rmSync(PARTS, {recursive: true, force: true});
mkdirSync(PARTS, {recursive: true});

const synth = (text, ls, file) =>
  execFileSync('piper', ['-m', VOICE, '--length_scale', String(ls), '-f', file], {input: text});

const buildStem = (lines, out) => {
  lines.forEach((l, i) => {
    l.file = `${PARTS}/${out.replace(/[^a-z0-9]/gi, '_')}_${i}.wav`;
    synth(l.t, l.ls, l.file);
  });

  // Inputs: 6 voice lines, then music, then the car-engine slice.
  const inputs = [
    ...lines.flatMap((l) => ['-i', l.file]),
    '-i', MUSIC,
    '-ss', String(CAR_SS), '-t', String(CAR_LEN), '-i', CAR,
  ];
  const mIdx = lines.length; // music
  const cIdx = lines.length + 1; // car

  const voDelays = lines.map((l, i) => `[${i}:a]adelay=${l.delay + LEAD}|${l.delay + LEAD}[d${i}]`).join(';');
  const voMixIn = lines.map((_, i) => `[d${i}]`).join('');

  const filter =
    // Voice: place each line, mix, master to a clean, present lead, go stereo.
    `${voDelays};${voMixIn}amix=inputs=${lines.length}:normalize=0:dropout_transition=0[voraw];` +
    `[voraw]highpass=f=90,equalizer=f=3200:t=q:w=1.6:g=2.5,` +
    `acompressor=threshold=-18dB:ratio=3:attack=8:release=160,loudnorm=I=-15:TP=-1.5:LRA=11,` +
    `aformat=channel_layouts=stereo,apad,atrim=0:${TOTAL}[vo];` +
    `[vo]asplit=2[voa][vok];` +
    // Music: present "gap" level, stereo; this is what fills the silence.
    `[${mIdx}:a]atrim=0:${TOTAL},asetpts=N/SR/TB,loudnorm=I=-19:TP=-2:LRA=11,aformat=channel_layouts=stereo[music];` +
    // Duck the music under the voice; it swells back up in the gaps (release).
    `[music][vok]sidechaincompress=threshold=0.04:ratio=7:attack=12:release=340:makeup=1[mduck];` +
    // Car engine: tamed texture under the hook, stereo.
    `[${cIdx}:a]highpass=f=70,lowpass=f=5200,afade=t=in:st=0:d=0.4,afade=t=out:st=${CAR_LEN - 0.7}:d=0.7,` +
    `volume=0.4,adelay=${CAR_DELAY}|${CAR_DELAY},aformat=channel_layouts=stereo[car];` +
    // Sum and master to a social-ready loudness, true-peak safe.
    `[voa][mduck][car]amix=inputs=3:normalize=0:dropout_transition=0[premix];` +
    `[premix]apad,atrim=0:${TOTAL},alimiter=limit=0.95,loudnorm=I=-14:TP=-1:LRA=11[outm]`;

  execFileSync(ffmpeg, ['-y', ...inputs, '-filter_complex', filter, '-map', '[outm]', '-ar', '48000', '-ac', '2', out],
    {stdio: 'inherit'});
  process.stdout.write(`\nMaster written: ${out}\n`);
};

buildStem([...COMMON, CTA_LINE.telegram], `${process.cwd()}/public/audio/vo-en-g1.wav`);
buildStem([...COMMON, CTA_LINE.web], `${process.cwd()}/public/audio/vo-en-g1-web.wav`);
