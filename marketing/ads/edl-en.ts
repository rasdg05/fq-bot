/**
 * EDL EN — English-narrated version of the car ad (g1).
 *
 * Same visuals and exact scene durations as `g1-perfil` (so the pre-built
 * voiceover track lines up frame-for-frame), but:
 *  - the presenter's original Spanish audio is muted (AdMovie `muteClips`),
 *  - an English narration master plays on top (public/audio/vo-en-g1.wav),
 *    which already carries the rescued car-engine ambience under the voice,
 *  - captions, CTA and disclaimer render in English (`lang: 'en'`).
 *
 * Compliant: no profit promises, risk disclaimer on the final frame.
 */
import type {Ad} from './edl';

const s = (sec: number) => Math.round(sec * 30);

const intro = {type: 'intro', durationInFrames: s(1)} as const;

export const ADS_EN: Ad[] = [
  {
    id: 'g1-en',
    title: 'EN · car → Telegram (English voiceover)',
    scenes: [
      intro,
      // Hook over the car shot (presenter clip + car B-roll overlay).
      {
        type: 'clip',
        durationInFrames: s(7.2),
        src: 'IMG_1846',
        inSec: 1.3,
        outSec: 8.5,
        audio: true,
        emphasize: true,
        overlay: {src: 'IMG_1835', inSec: 3, frames: 90},
        caption: 'Why most people will never drive one of these',
      },
      // Body — same cuts as the Spanish BODY, English captions.
      {
        type: 'clip',
        durationInFrames: s(4.8),
        src: 'IMG_1849',
        inSec: 12.0,
        outSec: 16.8,
        audio: true,
        caption: "The market didn't rob you. You robbed yourself.",
      },
      {
        type: 'clip',
        durationInFrames: s(3.6),
        src: 'IMG_1848',
        inSec: 7.4,
        outSec: 11.0,
        audio: true,
        caption: 'They buy on a feeling. They sell on fear.',
      },
      {
        type: 'clip',
        durationInFrames: s(6.55),
        src: 'IMG_1846',
        inSec: 9.3,
        outSec: 15.85,
        audio: true,
        caption: 'Lean on a system. A bot: Fibonacci Quantum.',
      },
      {type: 'showcase', durationInFrames: s(5), caption: 'Entry, stop and target. Zero emotion.'},
      {type: 'cta', durationInFrames: s(5), target: 'telegram'},
    ],
  },
];

/** Mastered English narration stem per ad id (staticFile path). */
export const VOICEOVER_EN: Record<string, string> = {
  'g1-en': 'audio/vo-en-g1.wav',
};
