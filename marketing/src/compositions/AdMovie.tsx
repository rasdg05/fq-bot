import React from 'react';
import {AbsoluteFill, Series} from 'remotion';
import type {Ad, Scene} from '../../ads/edl';
import {COLORS} from '../brand/tokens';
import {Disclaimer} from '../brand/Disclaimer';
import {Captions} from '../components/Captions';
import {Hook} from '../components/Hook';
import {ClipSegment} from '../components/ClipSegment';
import {AppShowcase} from '../components/AppShowcase';
import {CTA} from '../components/CTA';
import {Intro} from '../components/Intro';

const renderScene = (scene: Scene) => {
  switch (scene.type) {
    case 'intro':
      return <Intro />;
    case 'hook':
      return <Hook text={scene.text} kicker={scene.kicker} />;
    case 'clip':
      return <ClipSegment src={scene.src} inSec={scene.inSec} outSec={scene.outSec} note={scene.note} />;
    case 'showcase':
      return <AppShowcase />;
    case 'cta':
      return <CTA target={scene.target} />;
  }
};

const caption = (scene: Scene): string | undefined =>
  'caption' in scene ? scene.caption : undefined;

/**
 * Ensambla un anuncio completo a partir de su EDL: escenas en serie,
 * subtitulos por escena y microtexto legal persistente.
 */
export const AdMovie: React.FC<{ad: Ad}> = ({ad}) => {
  return (
    <AbsoluteFill style={{background: COLORS.bg}}>
      <Series>
        {ad.scenes.map((scene, i) => (
          <Series.Sequence key={i} durationInFrames={scene.durationInFrames}>
            {renderScene(scene)}
            {caption(scene) ? <Captions text={caption(scene) as string} /> : null}
          </Series.Sequence>
        ))}
      </Series>
      <Disclaimer />
    </AbsoluteFill>
  );
};
