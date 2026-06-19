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

/** Cuerpo central — cortes alineados a frases completas (sin cortar a media oración). */
const BODY: Scene[] = [
  // "No, bro. El mercado no te robó, te robaste tú solo por operar sin sistema."
  {type: 'clip', durationInFrames: s(4.8), src: 'IMG_1849', inSec: 12.0, outSec: 16.8, audio: true,
    note: 'reframe (frase completa)', caption: 'El mercado no te robó. Te robaste tú solo.'},
  // "Compran porque sienten que va a subir, venden por miedo."
  {type: 'clip', durationInFrames: s(3.6), src: 'IMG_1848', inSec: 7.4, outSec: 11.0, audio: true,
    note: 'corazonada / miedo', caption: 'Compran por corazonada. Venden por miedo.'},
  // "Cuando dejas de operar y te apoyas en un sistema, en un bot, como Fibonacci."
  {type: 'clip', durationInFrames: s(6.1), src: 'IMG_1846', inSec: 9.3, outSec: 15.4, audio: true,
    note: 'ego -> sistema -> FQ (corta antes de la promesa)', caption: 'Apóyate en un sistema. En un bot: Fibonacci Cuántico.'},
  // Señal en vivo (mockup del bot, multi-simbolo).
  {type: 'showcase', durationInFrames: s(5), caption: 'Entrada, stop y target. Cero emoción.'},
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
      hook('IMG_1846', 1.3, 8.5, '¿Por qué la mayoría nunca manejará uno de estos?'),
      ...BODY,
      cta('instagram'),
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
  {
    id: 'g3-roto',
    title: 'Gancho C · "sigues igual de roto" (CTA bot + IG)',
    scenes: [
      intro,
      // IMG_1844: "llevas anios haciendo trading y sigues igual de roto"
      hook('IMG_1844', 3.0, 7.0, 'Llevas años y sigues igual de roto.'),
      ...BODY,
      cta('both'),
    ],
  },
  {
    id: 'g4-producto',
    title: 'Gancho D · producto directo (CTA bot)',
    scenes: [
      intro,
      // IMG_1851: "esto es Fibonacci cuantico un bot preciso... entrada, stop, target"
      hook('IMG_1851', 0.0, 4.0, 'Un bot que te da entrada, stop y target.'),
      ...BODY,
      cta('bot'),
    ],
  },
];
