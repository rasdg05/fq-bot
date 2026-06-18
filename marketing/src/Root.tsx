import React from 'react';
import {Composition} from 'remotion';
import {ADS, totalFrames} from '../ads/edl';
import {VIDEO} from './brand/tokens';
import {AdMovie} from './compositions/AdMovie';
import {AppShowcase} from './components/AppShowcase';

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
            durationInFrames={totalFrames(ad)}
            fps={VIDEO.fps}
            width={VIDEO.width}
            height={VIDEO.height}
            defaultProps={{ad, frameMode: 'cover' as const}}
          />
          <Composition
            id={`${ad.id}-banda`}
            component={AdMovie}
            durationInFrames={totalFrames(ad)}
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
