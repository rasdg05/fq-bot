import React from 'react';
import {COLORS} from './tokens';

/** Separador hairline horizontal. */
export const Rule: React.FC<{width?: number | string; color?: string; opacity?: number}> = ({
  width = '100%',
  color = COLORS.hairline,
  opacity = 1,
}) => <div style={{width, height: 1, background: color, opacity}} />;

/** Acento vertical de marca (la "│" de FQ, en forma de barra). */
export const VAccent: React.FC<{height?: number; color?: string}> = ({
  height = 44,
  color = COLORS.accent,
}) => <div style={{width: 3, height, background: color, borderRadius: 2}} />;
