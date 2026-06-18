import React from 'react';
import {AbsoluteFill, Audio, Series, staticFile} from 'remotion';
import type {Ad, Scene} from '../../ads/edl';
import {COLORS, MUSIC} from '../brand/tokens';
import {Disclaimer} from '../brand/Disclaimer';
import {Captions} from '../components/Captions';
import {HookCaption} from '../components/HookCaption';
import {Hook} from '../components/Hook';
import {ClipSegment, type FrameMode} from '../components/ClipSegment';
import {AppShowcase} from '../components/AppShowcase';
import {CTA} from '../components/CTA';
import {Intro} from '../components/Intro';

const renderScene = (scene: Scene, frameMode: FrameMode) => {
  switch (scene.type) {
    case 'intro':
      return <Intro />;
    case 'hook':
      return <Hook text={scene.text} kicker={scene.kicker} />;
    case 'clip':
      return (
        <ClipSegment
          src={scene.src}
          inSec={scene.inSec}
          outSec={scene.outSec}
          audio={scene.audio}
          frameMode={frameMode}
          note={scene.note}
        />
      );
    case 'showcase':
      return <AppShowcase />;
    case 'cta':
      return <CTA target={scene.target} />;
  }
};

const caption = (scene: Scene): string | undefined =>
  'caption' in scene ? scene.caption : undefined;

/**
 * Ensambla un anuncio: escenas en serie, subtitulos por escena, cama musical
 * (mixto: la voz del presentador vive en los clips con audio:true) y microtexto
 * legal persistente. frameMode controla el encuadre del footage.
 */
export const AdMovie: React.FC<{ad: Ad; frameMode?: FrameMode}> = ({ad, frameMode = 'cover'}) => {
  return (
    <AbsoluteFill style={{background: COLORS.bg}}>
      {MUSIC.enabled ? <Audio src={staticFile(MUSIC.file)} volume={MUSIC.volume} loop /> : null}
      <Series>
        {ad.scenes.map((scene, i) => (
          <Series.Sequence key={i} durationInFrames={scene.durationInFrames}>
            {renderScene(scene, frameMode)}
            {caption(scene)
              ? scene.type === 'clip' && scene.emphasize
                ? <HookCaption text={caption(scene) as string} />
                : <Captions text={caption(scene) as string} />
              : null}
          </Series.Sequence>
        ))}
      </Series>
      <Disclaimer />
    </AbsoluteFill>
  );
};
