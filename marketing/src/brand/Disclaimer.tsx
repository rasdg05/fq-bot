import React from 'react';
import {AbsoluteFill} from 'remotion';
import {BRAND, BRAND_EN, COLORS, FONTS} from './tokens';

/**
 * Microtexto legal persistente. Obligatorio en toda creatividad:
 * sin promesas de rentabilidad (legal.py + politica de productos
 * financieros de Meta).
 */
export const Disclaimer: React.FC<{lang?: 'es' | 'en'}> = ({lang = 'es'}) => (
  <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', pointerEvents: 'none'}}>
    <div
      style={{
        marginBottom: 36,
        maxWidth: 920,
        textAlign: 'center',
        fontFamily: FONTS.sans,
        fontSize: 19,
        lineHeight: 1.35,
        letterSpacing: 0.2,
        color: COLORS.inkFaint,
      }}
    >
      {lang === 'en' ? BRAND_EN.disclaimer : BRAND.disclaimer}
    </div>
  </AbsoluteFill>
);
