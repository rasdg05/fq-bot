import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {COLORS, FONTS} from '../brand/tokens';

/**
 * Subtitulo de escena, anclado abajo (sobre el disclaimer). Fade in rapido.
 * Mantener lineas cortas: la mayoria ve los ads sin sonido.
 */
export const Captions: React.FC<{text: string}> = ({text}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 8], [0, 1], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', pointerEvents: 'none'}}>
      <div
        style={{
          marginBottom: 96,
          maxWidth: 900,
          textAlign: 'center',
          opacity,
          fontFamily: FONTS.sans,
          fontWeight: 700,
          fontSize: 46,
          lineHeight: 1.2,
          color: COLORS.ink,
          textShadow: '0 2px 18px rgba(0,0,0,0.85)',
        }}
      >
        {text}
      </div>
    </AbsoluteFill>
  );
};
