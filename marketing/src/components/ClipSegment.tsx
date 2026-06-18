import React from 'react';
import {AbsoluteFill, OffthreadVideo, staticFile, useVideoConfig} from 'remotion';
import {COLORS, FONTS, FOOTAGE_AVAILABLE, GLYPHS} from '../brand/tokens';

export type ClipProps = {
  /** Nombre del archivo sin extension en marketing/public/footage/<src>.mp4 */
  src: string;
  /** Segundo de inicio dentro del clip fuente. */
  inSec?: number;
  /** Segundo de fin dentro del clip fuente. */
  outSec?: number;
  /** Etiqueta visible en el slate cuando aun no hay footage. */
  note?: string;
};

/**
 * Segmento de footage. Si FOOTAGE_AVAILABLE es false, muestra un slate de
 * marca con el clip y el rango previsto, asi el anuncio se renderiza completo
 * sin depender de los archivos. Cuando metas el footage y corras `npm run
 * ingest`, pon FOOTAGE_AVAILABLE en true en tokens.ts.
 */
export const ClipSegment: React.FC<ClipProps> = ({src, inSec = 0, outSec, note}) => {
  const {fps} = useVideoConfig();

  if (!FOOTAGE_AVAILABLE) {
    return (
      <AbsoluteFill
        style={{
          background: COLORS.panel,
          justifyContent: 'center',
          alignItems: 'center',
          border: `1px solid ${COLORS.hairline}`,
        }}
      >
        <div style={{fontFamily: FONTS.mono, color: COLORS.inkDim, fontSize: 26, letterSpacing: 4}}>
          {GLYPHS.title} CLIP
        </div>
        <div style={{fontFamily: FONTS.sans, color: COLORS.ink, fontSize: 40, fontWeight: 700, marginTop: 16}}>
          {src}
        </div>
        <div style={{fontFamily: FONTS.mono, color: COLORS.inkFaint, fontSize: 24, marginTop: 12}}>
          {inSec.toFixed(1)}s {GLYPHS.bulletAct} {outSec ? `${outSec.toFixed(1)}s` : 'fin'}
        </div>
        {note ? (
          <div style={{fontFamily: FONTS.sans, color: COLORS.inkDim, fontSize: 26, marginTop: 24, maxWidth: 720, textAlign: 'center'}}>
            {note}
          </div>
        ) : null}
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill style={{background: COLORS.bg}}>
      <OffthreadVideo
        src={staticFile(`footage/${src}.mp4`)}
        startFrom={Math.round(inSec * fps)}
        endAt={outSec ? Math.round(outSec * fps) : undefined}
        style={{width: '100%', height: '100%', objectFit: 'cover'}}
      />
    </AbsoluteFill>
  );
};
