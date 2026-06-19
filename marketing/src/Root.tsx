import React from 'react';
import {Composition} from 'remotion';
import {ADS, totalFrames} from '../ads/edl';
import {VIDEO} from './brand/tokens';
import {AdMovie, TRANSITION} from './compositions/AdMovie';
import {AppShowcase} from './components/AppShowcase';

// Las transiciones solapan frames entre escenas: restamos ese solape.
const adDuration = (ad: (typeof ADS)[number]) =>
  totalFrames(ad) - Math.max(0, ad.scenes.length - 1) * TRANSITION;

/**
 * Por cada anuncio del EDL se registran DOS composiciones: encuadre "cover"
 * (recorta al 9:16) y "banda" (clip completo + fondo de marca). Mas el
 * showcase del bot suelto.
 */
export const RemotionRoot: React.FC = () => {
  return (
    <>
      {ADS.map((ad) => (
        <React.Fragment key={ad.id}>
          <Composition
            id={`${ad.id}-cover`}
            component={AdMovie}
            durationInFrames={adDuration(ad)}
            fps={VIDEO.fps}
            width={VIDEO.width}
            height={VIDEO.height}
            defaultProps={{ad, frameMode: 'cover' as const}}
          />
          <Composition
            id={`${ad.id}-banda`}
            component={AdMovie}
            durationInFrames={adDuration(ad)}
            fps={VIDEO.fps}
            width={VIDEO.width}
            height={VIDEO.height}
            defaultProps={{ad, frameMode: 'band' as const}}
          />
        </React.Fragment>
      ))}

      <Composition
        id="showcase-app"
        component={AppShowcase}
        durationInFrames={VIDEO.fps * 8}
        fps={VIDEO.fps}
        width={VIDEO.width}
        height={VIDEO.height}
      />
    </>
  );
};
