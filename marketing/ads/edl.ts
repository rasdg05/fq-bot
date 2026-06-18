/**
 * EDL — Edit Decision List de FQ.
 *
 * Versiones de anuncio como datos. Los clips referencian el footage real
 * (marketing/public/footage/<name>.mp4) por nombre + rango (in/out en seg).
 *
 * Flujo: ajustas rangos -> npm run dev (Studio) -> npm run render:all.
 *
 * NOTA cumplimiento: el auto de lujo se usa como ambiente breve, nunca como
 * "esto vas a ganar". El copy va sobre proceso y disciplina.
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

export const ADS: Ad[] = [
  {
    id: 'a1-demo-app',
    title: 'A1 · Demo de la app (CTA bot)',
    scenes: [
      {type: 'intro', durationInFrames: s(1)},
      {type: 'clip', durationInFrames: s(3.5), src: 'IMG_1850', inSec: 1, outSec: 4.5, note: 'presentador sentado, explica', caption: 'El 90% de las senales son ruido.'},
      {type: 'showcase', durationInFrames: s(7), caption: 'FQ solo habla cuando hay ventaja en SOL/USDT.'},
      {type: 'clip', durationInFrames: s(3), src: 'IMG_1848', inSec: 4, outSec: 7, note: 'talking head buena luz', caption: 'Estructura, no humo.'},
      {type: 'cta', durationInFrames: s(3.5), target: 'bot'},
    ],
  },
  {
    id: 'a2-disciplina',
    title: 'A2 · Disciplina (CTA bot + IG)',
    scenes: [
      {type: 'intro', durationInFrames: s(1)},
      {type: 'clip', durationInFrames: s(3.5), src: 'IMG_1851', inSec: 1, outSec: 4.5, note: 'sentado, gesticula', caption: 'Deja de operar a ciegas.'},
      {type: 'showcase', durationInFrames: s(6), caption: 'Direccion, zona, invalidacion y gestion.'},
      {type: 'clip', durationInFrames: s(3), src: 'IMG_1844', inSec: 3, outSec: 6, note: 'talking head conduciendo', caption: 'Disciplina sistematica en SOL/USDT.'},
      {type: 'cta', durationInFrames: s(3.5), target: 'both'},
    ],
  },
  {
    id: 'a3-ig-linkme',
    title: 'A3 · Trafico a IG/Linkme',
    scenes: [
      {type: 'intro', durationInFrames: s(1)},
      {type: 'clip', durationInFrames: s(2.5), src: 'IMG_1835', inSec: 1, outSec: 3.5, note: 'B-roll auto (ambiente breve)', caption: 'Cuando hay ventaja, ejecuta.'},
      {type: 'clip', durationInFrames: s(3.5), src: 'IMG_1846', inSec: 5, outSec: 8.5, note: 'talking head con telefono', caption: 'Cuando no, espera.'},
      {type: 'showcase', durationInFrames: s(5), caption: 'Mira el proceso completo en el perfil.'},
      {type: 'cta', durationInFrames: s(3.5), target: 'instagram'},
    ],
  },
];
