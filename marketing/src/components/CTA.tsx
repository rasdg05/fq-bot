import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {BRAND, BRAND_EN, COLORS, CTA_CONFIG, FONTS, GLYPHS, COMMUNITY, COMMUNITY_EN, CTA_TEXT_EN} from '../brand/tokens';
import {VAccent} from '../brand/Rule';

export type CtaTarget = 'bot' | 'instagram' | 'both' | 'telegram' | 'web';

const Chip: React.FC<{label: string; value: string; delay: number; sub?: string}> = ({
  label,
  value,
  delay,
  sub,
}) => {
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
        padding: '20px 28px',
        minWidth: 620,
      }}
    >
      <span style={{fontFamily: FONTS.mono, fontSize: 34, color: COLORS.accent}}>{GLYPHS.bulletAct}</span>
      <div>
        <div style={{fontFamily: FONTS.mono, fontSize: 20, letterSpacing: 3, color: COLORS.inkDim, textTransform: 'uppercase'}}>
          {label}
        </div>
        <div style={{fontFamily: FONTS.sans, fontSize: 36, fontWeight: 800, color: COLORS.ink}}>{value}</div>
        {sub ? (
          <div style={{fontFamily: FONTS.mono, fontSize: 22, color: COLORS.inkDim, marginTop: 4}}>
            {GLYPHS.bulletChk} {sub}
          </div>
        ) : null}
      </div>
    </div>
  );
};

/** Cierre con oferta (3 dias gratis · sin tarjeta), escasez y destinos. */
export const CTA: React.FC<{target: CtaTarget; lang?: 'es' | 'en'}> = ({target, lang = 'es'}) => {
  const frame = useCurrentFrame();
  const wm = spring({frame, fps: 30, config: {damping: 200}});
  const offer = spring({frame: frame - 6, fps: 30, config: {damping: 200}});
  const en = lang === 'en';
  const community = en ? COMMUNITY_EN : COMMUNITY;

  return (
    <AbsoluteFill style={{background: COLORS.bg, justifyContent: 'center', alignItems: 'center', padding: 70}}>
      <div style={{display: 'flex', gap: 20, alignItems: 'center', opacity: wm, marginBottom: 34}}>
        <VAccent height={76} />
        <div>
          <div style={{fontFamily: FONTS.sans, fontWeight: 800, fontSize: 80, letterSpacing: -2, color: COLORS.ink}}>
            {BRAND.product}
          </div>
          <div style={{fontFamily: FONTS.mono, fontSize: 22, color: COLORS.inkDim, letterSpacing: 1}}>
            {en ? BRAND_EN.productLong : BRAND.productLong}
          </div>
        </div>
      </div>

      {/* Comunidad */}
      <div style={{opacity: offer, transform: `translateY(${interpolate(offer, [0, 1], [16, 0])}px)`, textAlign: 'center', marginBottom: 14}}>
        <div style={{fontFamily: FONTS.sans, fontWeight: 800, fontSize: 56, color: COLORS.ink}}>
          {community.join}
        </div>
        <div style={{fontFamily: FONTS.mono, fontSize: 26, color: COLORS.inkDim, marginTop: 8}}>
          {community.line}
        </div>
      </div>

      {/* Exclusividad suave (tribu) */}
      <div
        style={{
          opacity: offer,
          marginBottom: 36,
          padding: '10px 22px',
          border: `1px solid ${COLORS.hairline}`,
          borderRadius: 999,
          fontFamily: FONTS.mono,
          fontSize: 24,
          letterSpacing: 2,
          textTransform: 'uppercase',
          color: COLORS.long,
        }}
      >
        {community.note}
      </div>

      <div style={{display: 'flex', flexDirection: 'column', gap: 18}}>
        {(target === 'bot' || target === 'both') && (
          <Chip label={en ? CTA_TEXT_EN.bot : 'Entra al bot'} value={`@${CTA_CONFIG.botUsername}`} delay={12} />
        )}
        {target === 'telegram' && (
          <Chip
            label={en ? CTA_TEXT_EN.telegram : 'Escríbeme en Telegram'}
            value={`@${CTA_CONFIG.telegramUser}`}
            sub={
              en
                ? `${CTA_TEXT_EN.telegramSub} "${CTA_CONFIG.keyword}"`
                : `manda la palabra "${CTA_CONFIG.keyword}"`
            }
            delay={12}
          />
        )}
        {target === 'web' && (
          <Chip
            label={en ? CTA_TEXT_EN.webLabel : 'Descárgala gratis'}
            value={en ? CTA_TEXT_EN.webValue : 'Toca «Más información» ↓'}
            delay={12}
          />
        )}
        {(target === 'instagram' || target === 'both') && (
          <Chip
            label={en ? CTA_TEXT_EN.follow : 'Sigueme'}
            value={`@${CTA_CONFIG.instagram}`}
            sub={
              CTA_CONFIG.linkme
                ? `${en ? CTA_TEXT_EN.linkInBio : 'link en bio'} · ${CTA_CONFIG.linkme}`
                : undefined
            }
            delay={target === 'both' ? 20 : 12}
          />
        )}
      </div>
    </AbsoluteFill>
  );
};
