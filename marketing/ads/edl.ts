/**
 * EDL — Edit Decision List de FQ.
 *
 * Aqui se definen las VERSIONES de anuncio como datos: cada anuncio es una
 * lista de escenas. Los clips referencian tu footage por nombre + rango
 * (in/out en segundos). Mientras FOOTAGE_AVAILABLE sea false (tokens.ts) los
 * clips se ven como slate de marca, asi puedes previsualizar la estructura
 * antes de tener el video cortado.
 *
 * Flujo: ajustas rangos -> npm run dev (Studio) -> npm run render:all.
 */
import type {CtaTarget} from '../src/components/CTA';

export type Scene =
  | {type: 'intro'; durationInFrames: number}
  | {type: 'hook'; durationInFrames: number; text: string; kicker?: string; caption?: string}
  | {type: 'clip'; durationInFrames: number; src: string; inSec?: number; outSec?: number; note?: string; caption?: string}
  | {type: 'showcase'; durationInFrames: number; caption?: string}
  | {type: 'cta'; durationInFrames: number; target: CtaTarget};

export type Ad = {
  id: string;
  title: string;
  scenes: Scene[];
};

export const totalFrames = (ad: Ad): number =>
  ad.scenes.reduce((n, s) => n + s.durationInFrames, 0);

// 30 fps. Helper de segundos -> frames.
const s = (sec: number) => Math.round(sec * 30);

/**
 * 3 conceptos base. Los nombres de clip son ejemplos de tu carpeta de Drive
 * (pix4brain*, NO*). Reasigna in/out cuando revisemos los contact sheets.
 */
export const ADS: Ad[] = [
  {
    id: 'a1-no-al-ruido',
    title: 'A1 · No al ruido',
    scenes: [
      {type: 'intro', durationInFrames: s(1)},
      {type: 'hook', durationInFrames: s(2.5), kicker: 'SOL/USDT', text: 'El 90% de las senales son ruido.', caption: 'El 90% de las senales son ruido.'},
      {type: 'clip', durationInFrames: s(4), src: 'NO', inSec: 2, outSec: 6, note: 'Momento "NO opero": disciplina, no FOMO', caption: 'Cuando no hay ventaja, FQ calla.'},
      {type: 'showcase', durationInFrames: s(7), caption: 'Cuando la hay, ejecuta con estructura.'},
      {type: 'cta', durationInFrames: s(3.5), target: 'both'},
    ],
  },
  {
    id: 'a2-demo-app',
    title: 'A2 · Demo de la app',
    scenes: [
      {type: 'intro', durationInFrames: s(1)},
      {type: 'hook', durationInFrames: s(2.5), kicker: 'Mesa de liquidez', text: 'Asi se ve una senal de FQ.', caption: 'Asi se ve una senal de FQ.'},
      {type: 'showcase', durationInFrames: s(8), caption: 'Direccion, zona, invalidacion y gestion.'},
      {type: 'clip', durationInFrames: s(3), src: 'pix4brain1-SEPT', inSec: 5, outSec: 8, note: 'Talking head: por que importa la estructura', caption: 'Sin emoji, sin humo. Estructura.'},
      {type: 'cta', durationInFrames: s(3.5), target: 'bot'},
    ],
  },
  {
    id: 'a3-perfil-insta',
    title: 'A3 · Trafico a Instagram',
    scenes: [
      {type: 'intro', durationInFrames: s(1)},
      {type: 'hook', durationInFrames: s(2.5), text: 'Disciplina sistematica en SOL/USDT.', caption: 'Disciplina sistematica en SOL/USDT.'},
      {type: 'clip', durationInFrames: s(4.5), src: 'pix4brain28-AGS', inSec: 1, outSec: 5.5, note: 'Hook fuerte de presentador', caption: 'Cuando hay ventaja, ejecuta. Cuando no, espera.'},
      {type: 'showcase', durationInFrames: s(5), caption: 'Mira el proceso completo en el perfil.'},
      {type: 'cta', durationInFrames: s(3.5), target: 'instagram'},
    ],
  },
];
