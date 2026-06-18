/**
 * EDL — FQ (Fibonacci Cuantico). Modelo del brief de RasDG:
 *
 *   "Grabas el CUERPO una vez y le montas encima cualquiera de los ganchos."
 *
 * BODY = cuerpo central compartido (seg 3-30 del guion).
 * Cada anuncio = intro + un GANCHO (0-3s, palabra-por-palabra) + BODY + CTA.
 *
 * Construido sobre el discurso REAL transcrito (public/audio/transcripts.json)
 * y solo con segmentos COMPATIBLES con Meta (sin promesas de ganancias).
 *
 * audio:true conserva la voz del presentador; emphasize:true resalta el
 * subtitulo palabra por palabra (para el gancho).
 *
 * FALTA POR GRABAR (no esta en el footage actual):
 *  - Linea de blindaje legal exacta: "No te prometo que vas a manejar esto".
 *  - Captura/recording real del bot para el segmento de senal en vivo
 *    (ahora se cubre con el mockup Remotion, sin cifras inventadas).
 */
import type {CtaTarget} from '../src/components/CTA';
import type {FrameMode} from '../src/components/ClipSegment';

export type Scene =
  | {type: 'intro'; durationInFrames: number}
  | {type: 'hook'; durationInFrames: number; text: string; kicker?: string; caption?: string}
  | {type: 'clip'; durationInFrames: number; src: string; inSec?: number; outSec?: number; audio?: boolean; emphasize?: boolean; note?: string; caption?: string}
  | {type: 'showcase'; durationInFrames: number; caption?: string}
  | {type: 'cta'; durationInFrames: number; target: CtaTarget};

export type Ad = {
  id: string;
  title: string;
  scenes: Scene[];
};

export type {FrameMode};

export const totalFrames = (ad: Ad): number =>
  ad.scenes.reduce((n, s) => n + s.durationInFrames, 0);

const s = (sec: number) => Math.round(sec * 30);

const intro: Scene = {type: 'intro', durationInFrames: s(1)};

/** Cuerpo central — se graba/usa una sola vez. */
const BODY: Scene[] = [
  // [3-8] Reframe brutal. "El mercado no te robo, te robaste tu solo."
  {type: 'clip', durationInFrames: s(5), src: 'IMG_1849', inSec: 10.0, outSec: 15.0, audio: true,
    note: 'reframe', caption: 'El mercado no te robo. Te robaste tu solo.'},
  // [8-14] "...entran y adivinan, compran porque sienten, venden por miedo."
  {type: 'clip', durationInFrames: s(5.6), src: 'IMG_1848', inSec: 0.9, outSec: 6.5, audio: true,
    note: 'adivinar / miedo', caption: 'Entraste a adivinar. Vendiste por miedo.'},
  // [14-19] Ego -> sistema -> FQ (corta antes de "los resultados llegan solos").
  {type: 'clip', durationInFrames: s(5), src: 'IMG_1846', inSec: 8.6, outSec: 13.6, audio: true,
    note: 'ego -> FQ', caption: 'Deja el ego. Opera con matematica: Fibonacci Cuantico.'},
  // [19-25] Senal en vivo (mockup del bot, multi-simbolo, sin cifras inventadas).
  {type: 'showcase', durationInFrames: s(6), caption: 'Senal lista: entrada, stop, target. Cero emocion.'},
  // [25-28] Blindaje (parcial — falta la linea exacta del auto, ver nota arriba).
  {type: 'clip', durationInFrames: s(3.2), src: 'IMG_1850', inSec: 1.8, outSec: 5.0, audio: true,
    note: 'blindaje parcial', caption: 'No te vendo un sueno. Te doy el sistema que uso.'},
];

/** Gancho: clip corto con voz + subtitulo palabra-por-palabra. */
const hook = (src: string, inSec: number, outSec: number, caption: string): Scene => ({
  type: 'clip',
  durationInFrames: s(outSec - inSec),
  src,
  inSec,
  outSec,
  audio: true,
  emphasize: true,
  caption,
});

const cta = (target: CtaTarget): Scene => ({type: 'cta', durationInFrames: s(5), target});

export const ADS: Ad[] = [
  {
    id: 'g1-auto',
    title: 'Gancho A · auto (CTA bot)',
    scenes: [
      intro,
      hook('IMG_1846', 1.6, 4.6, 'Por que la mayoria nunca va a manejar uno de estos?'),
      ...BODY,
      cta('bot'),
    ],
  },
  {
    id: 'g2-pierde',
    title: 'Gancho B · "la mayoria pierde" (CTA bot + IG)',
    scenes: [
      intro,
      hook('IMG_5979', 0.2, 4.8, 'La mayoria pierde por no tener un sistema.'),
      ...BODY,
      cta('both'),
    ],
  },
];
