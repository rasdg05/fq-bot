import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {COLORS, FONTS} from '../brand/tokens';

/**
 * Subtitulo del gancho con resaltado palabra por palabra. Reparte las palabras
 * a lo largo de la duracion de la escena; la palabra "activa" se enciende.
 * Pensado para los primeros 3s (retencion).
 */
export const HookCaption: React.FC<{text: string}> = ({text}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const words = text.split(' ');
  const per = durationInFrames / Math.max(words.length, 1);
  const active = Math.floor(frame / per);

  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', padding: 70, pointerEvents: 'none'}}>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: '10px 16px',
          maxWidth: 940,
          textAlign: 'center',
        }}
      >
        {words.map((w, i) => {
          const shown = i <= active;
          const isActive = i === active;
          return (
            <span
              key={i}
              style={{
                fontFamily: FONTS.sans,
                fontWeight: 800,
                fontSize: 62,
                lineHeight: 1.1,
                letterSpacing: -1,
                opacity: shown ? 1 : 0.18,
                color: isActive ? COLORS.bg : COLORS.ink,
                background: isActive ? COLORS.ink : 'transparent',
                padding: isActive ? '2px 12px' : '2px 0',
                borderRadius: 8,
                transform: `scale(${interpolate(isActive ? 1 : 0, [0, 1], [1, 1.04])})`,
                textShadow: isActive ? 'none' : '0 2px 16px rgba(0,0,0,0.85)',
              }}
            >
              {w}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
