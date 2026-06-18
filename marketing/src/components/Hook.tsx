import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {COLORS, FONTS, GLYPHS} from '../brand/tokens';
import {VAccent} from '../brand/Rule';

/**
 * Gancho de apertura (0-3s). Texto grande, entrada con spring, acento
 * vertical de marca. Sobrio, alto contraste para los primeros fotogramas.
 */
export const Hook: React.FC<{text: string; kicker?: string}> = ({text, kicker}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = spring({frame, fps, config: {damping: 200}});
  const y = interpolate(enter, [0, 1], [40, 0]);

  return (
    <AbsoluteFill style={{background: COLORS.bg, justifyContent: 'center', padding: 90}}>
      <div style={{transform: `translateY(${y}px)`, opacity: enter}}>
        {kicker ? (
          <div
            style={{
              fontFamily: FONTS.mono,
              fontSize: 28,
              letterSpacing: 6,
              textTransform: 'uppercase',
              color: COLORS.inkDim,
              marginBottom: 28,
            }}
          >
            {GLYPHS.title} {kicker}
          </div>
        ) : null}
        <div style={{display: 'flex', gap: 28, alignItems: 'stretch'}}>
          <VAccent height={text.length > 40 ? 320 : 220} />
          <div
            style={{
              fontFamily: FONTS.sans,
              fontWeight: 800,
              fontSize: 84,
              lineHeight: 1.04,
              letterSpacing: -1.5,
              color: COLORS.ink,
            }}
          >
            {text}
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
