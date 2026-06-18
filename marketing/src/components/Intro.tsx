import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {BRAND, COLORS, FONTS} from '../brand/tokens';
import {VAccent} from '../brand/Rule';

/** Bumper de marca corto (wordmark FQ con acento vertical). */
export const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const e = spring({frame, fps, config: {damping: 200}});
  const out = interpolate(frame, [durationInFrames - 8, durationInFrames], [1, 0], {extrapolateLeft: 'clamp'});

  return (
    <AbsoluteFill style={{background: COLORS.bg, justifyContent: 'center', alignItems: 'center'}}>
      <div style={{display: 'flex', gap: 22, alignItems: 'center', opacity: Math.min(e, out)}}>
        <VAccent height={interpolate(e, [0, 1], [0, 96])} />
        <div style={{fontFamily: FONTS.sans, fontWeight: 800, fontSize: 130, letterSpacing: -3, color: COLORS.ink}}>
          {BRAND.product}
        </div>
      </div>
    </AbsoluteFill>
  );
};
