import React from 'react';
import {Composition} from 'remotion';
import {ADS, totalFrames} from '../ads/edl';
import {VIDEO} from './brand/tokens';
import {AdMovie} from './compositions/AdMovie';
import {AppShowcase} from './components/AppShowcase';

/**
 * Una Composition por anuncio del EDL + el showcase de la app suelto
 * (util para reusar el mockup del bot en otras piezas).
 */
export const RemotionRoot: React.FC = () => {
  return (
    <>
      {ADS.map((ad) => (
        <Composition
          key={ad.id}
          id={ad.id}
          component={AdMovie}
          durationInFrames={totalFrames(ad)}
          fps={VIDEO.fps}
          width={VIDEO.width}
          height={VIDEO.height}
          defaultProps={{ad}}
        />
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
