import React from 'react';
import {AbsoluteFill, Audio, interpolate, staticFile} from 'remotion';
import {TransitionSeries, linearTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
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

/** Frames de crossfade entre escenas. */
export const TRANSITION = 8;

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

const SceneWithCaption: React.FC<{scene: Scene; frameMode: FrameMode}> = ({scene, frameMode}) => {
  const cap = caption(scene);
  return (
    <AbsoluteFill>
      {renderScene(scene, frameMode)}
      {cap ? (
        scene.type === 'clip' && scene.emphasize ? (
          <HookCaption text={cap} />
        ) : (
          <Captions text={cap} />
        )
      ) : null}
    </AbsoluteFill>
  );
};

/**
 * Ensambla un anuncio con crossfades entre escenas, subtitulos, cama musical
 * y microtexto legal persistente.
 */
export const AdMovie: React.FC<{ad: Ad; frameMode?: FrameMode}> = ({ad, frameMode = 'cover'}) => {
  // Volumen de musica dinamico: baja bajo la voz, sube cuando no hay voz.
  // Nunca llega a cero -> siempre hay una "frecuencia presente".
  const VOICE_VOL = 0.12;
  const FULL_VOL = 0.5;
  const starts: number[] = [];
  let acc = 0;
  ad.scenes.forEach((s, i) => {
    starts.push(acc - i * TRANSITION);
    acc += s.durationInFrames;
  });
  const points = ad.scenes.map((s, i) => ({
    f: starts[i] + s.durationInFrames / 2,
    v: s.type === 'clip' && s.audio ? VOICE_VOL : FULL_VOL,
  }));
  const musicVolume = (f: number) =>
    points.length > 1
      ? interpolate(
          f,
          points.map((p) => p.f),
          points.map((p) => p.v),
          {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
        )
      : FULL_VOL;

  return (
    <AbsoluteFill style={{background: COLORS.bg}}>
      {MUSIC.enabled ? <Audio src={staticFile(MUSIC.file)} volume={musicVolume} loop /> : null}
      <TransitionSeries>
        {ad.scenes.flatMap((scene, i) => {
          const seq = (
            <TransitionSeries.Sequence key={`s${i}`} durationInFrames={scene.durationInFrames}>
              <SceneWithCaption scene={scene} frameMode={frameMode} />
            </TransitionSeries.Sequence>
          );
          if (i === 0) return [seq];
          return [
            <TransitionSeries.Transition
              key={`t${i}`}
              timing={linearTiming({durationInFrames: TRANSITION})}
              presentation={fade()}
            />,
            seq,
          ];
        })}
      </TransitionSeries>
      <Disclaimer />
    </AbsoluteFill>
  );
};
