import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {BRAND, COLORS, CTA_CONFIG, FONTS, GLYPHS} from '../brand/tokens';
import {VAccent} from '../brand/Rule';

export type CtaTarget = 'bot' | 'instagram' | 'both';

const Chip: React.FC<{label: string; value: string; delay: number}> = ({label, value, delay}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const e = spring({frame: frame - delay, fps, config: {damping: 200}});
  return (
    <div
      style={{
        opacity: e,
        transform: `translateY(${interpolate(e, [0, 1], [20, 0])}px)`,
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        background: COLORS.panel,
        border: `1px solid ${COLORS.hairline}`,
        borderRadius: 16,
        padding: '22px 30px',
        minWidth: 620,
      }}
    >
      <span style={{fontFamily: FONTS.mono, fontSize: 34, color: COLORS.accent}}>{GLYPHS.bulletAct}</span>
      <div>
        <div style={{fontFamily: FONTS.mono, fontSize: 20, letterSpacing: 3, color: COLORS.inkDim, textTransform: 'uppercase'}}>
          {label}
        </div>
        <div style={{fontFamily: FONTS.sans, fontSize: 38, fontWeight: 800, color: COLORS.ink}}>{value}</div>
      </div>
    </div>
  );
};

/** Cierre con llamada a la accion. Soporta bot, instagram o ambos. */
export const CTA: React.FC<{target: CtaTarget}> = ({target}) => {
  const frame = useCurrentFrame();
  const wm = spring({frame, fps: 30, config: {damping: 200}});

  return (
    <AbsoluteFill style={{background: COLORS.bg, justifyContent: 'center', alignItems: 'center', padding: 80}}>
      <div style={{display: 'flex', gap: 22, alignItems: 'center', opacity: wm, marginBottom: 56}}>
        <VAccent height={88} />
        <div>
          <div style={{fontFamily: FONTS.sans, fontWeight: 800, fontSize: 96, letterSpacing: -2, color: COLORS.ink}}>
            {BRAND.product}
          </div>
          <div style={{fontFamily: FONTS.mono, fontSize: 24, color: COLORS.inkDim, letterSpacing: 1}}>
            {BRAND.tagline}
          </div>
        </div>
      </div>

      <div style={{display: 'flex', flexDirection: 'column', gap: 22}}>
        {(target === 'bot' || target === 'both') && (
          <Chip label="Abre el bot" value={`@${CTA_CONFIG.botUsername}`} delay={10} />
        )}
        {(target === 'instagram' || target === 'both') && (
          <Chip label="Siguenos" value={`@${CTA_CONFIG.instagram}`} delay={target === 'both' ? 18 : 10} />
        )}
      </div>
    </AbsoluteFill>
  );
};
