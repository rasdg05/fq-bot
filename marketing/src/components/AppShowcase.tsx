import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {BRAND, BRAND_EN, COLORS, FONTS, GLYPHS, CTA_TEXT_EN} from '../brand/tokens';
import {Rule} from '../brand/Rule';
import {PhoneFrame} from './PhoneFrame';

/** Linea del card que entra con spring escalonado. */
const Line: React.FC<{delay: number; children: React.ReactNode; mono?: boolean; dim?: boolean; size?: number}> = ({
  delay,
  children,
  mono,
  dim,
  size = 26,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const e = spring({frame: frame - delay, fps, config: {damping: 200}});
  return (
    <div
      style={{
        opacity: e,
        transform: `translateX(${interpolate(e, [0, 1], [16, 0])}px)`,
        fontFamily: mono ? FONTS.mono : FONTS.sans,
        fontSize: size,
        lineHeight: 1.4,
        color: dim ? COLORS.inkDim : COLORS.ink,
      }}
    >
      {children}
    </div>
  );
};

/**
 * Mockup animado del bot FQ en Telegram. Sustituye a la grabacion de
 * pantalla: muestra la "app" (el bot) construyendo una senal con el sistema
 * de glifos real. Sin P&L ni promesas — solo estructura y disciplina.
 */
export const AppShowcase: React.FC<{lang?: 'es' | 'en'}> = ({lang = 'es'}) => {
  const frame = useCurrentFrame();
  const cardEnter = spring({frame: frame - 8, fps: 30, config: {damping: 200}});
  const en = lang === 'en';

  return (
    <AbsoluteFill style={{background: COLORS.bg, justifyContent: 'center', alignItems: 'center'}}>
      <PhoneFrame>
        {/* Header del bot */}
        <div style={{padding: '70px 28px 16px', borderBottom: `1px solid ${COLORS.hairline}`}}>
          <div style={{display: 'flex', alignItems: 'center', gap: 14}}>
            <div
              style={{
                width: 56,
                height: 56,
                borderRadius: 12,
                background: COLORS.panelHi,
                border: `1px solid ${COLORS.hairline}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontFamily: FONTS.mono,
                fontWeight: 700,
                color: COLORS.ink,
                fontSize: 26,
              }}
            >
              {BRAND.product}
            </div>
            <div>
              <div style={{fontFamily: FONTS.sans, fontWeight: 700, color: COLORS.ink, fontSize: 26}}>
                {BRAND.product} {GLYPHS.title} {BRAND.desk}
              </div>
              <div style={{fontFamily: FONTS.mono, color: COLORS.inkDim, fontSize: 18}}>
                {en ? BRAND_EN.online : 'multi-simbolo · en linea'}
              </div>
            </div>
          </div>
        </div>

        {/* Cuerpo del chat: tarjeta de senal */}
        <div style={{flex: 1, padding: 24, display: 'flex', flexDirection: 'column', justifyContent: 'center'}}>
          <div
            style={{
              opacity: cardEnter,
              transform: `translateY(${interpolate(cardEnter, [0, 1], [24, 0])}px)`,
              background: COLORS.panel,
              border: `1px solid ${COLORS.hairline}`,
              borderRadius: 18,
              padding: 26,
            }}
          >
            <div style={{fontFamily: FONTS.mono, color: COLORS.inkFaint, fontSize: 22, marginBottom: 10}}>
              {GLYPHS.rule}
            </div>
            <Line delay={14} mono size={28}>
              <span style={{color: COLORS.accent}}>{GLYPHS.title}</span> {BRAND.product} · {BRAND.symbols[0]}
            </Line>
            <div style={{height: 6}} />
            <Line delay={18} mono dim size={20}>
              {BRAND.symbols.join('  ·  ')}  ·  +
            </Line>
            <div style={{height: 14}} />
            <Line delay={22} size={40}>
              <span style={{color: COLORS.long, fontWeight: 800}}>{GLYPHS.long} LONG</span>
            </Line>
            <div style={{height: 16}} />
            <Line delay={30} mono dim>
              {GLYPHS.bulletChk} {en ? CTA_TEXT_EN.signal.entry : 'Entrada definida'}
            </Line>
            <Line delay={36} mono dim>
              {GLYPHS.bulletChk} {en ? CTA_TEXT_EN.signal.stop : 'Stop definido'}
            </Line>
            <Line delay={42} mono dim>
              {GLYPHS.bulletChk} {en ? CTA_TEXT_EN.signal.target : 'Target por estructura'}
            </Line>
            <div style={{height: 16}} />
            <div style={{opacity: spring({frame: frame - 48, fps: 30, config: {damping: 200}})}}>
              <Rule />
            </div>
            <div style={{height: 12}} />
            <Line delay={52} size={22} dim>
              {GLYPHS.bulletAct} {en ? BRAND_EN.promise : BRAND.promise}
            </Line>
          </div>
        </div>
      </PhoneFrame>
    </AbsoluteFill>
  );
};
