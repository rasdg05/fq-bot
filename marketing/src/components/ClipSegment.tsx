import React from 'react';
import {AbsoluteFill, OffthreadVideo, staticFile, useVideoConfig} from 'remotion';
import {BRAND, COLORS, FONTS, FOOTAGE_AVAILABLE, GLYPHS} from '../brand/tokens';

export type FrameMode = 'cover' | 'band';

export type ClipProps = {
  /** Nombre del archivo sin extension en marketing/public/footage/<src>.mp4 */
  src: string;
  inSec?: number;
  outSec?: number;
  /** true = conserva el audio del clip (voz del presentador). */
  audio?: boolean;
  /** Encuadre: cover (recorta) o band (clip completo + fondo de marca). */
  frameMode?: FrameMode;
  note?: string;
};

export const ClipSegment: React.FC<ClipProps> = ({
  src,
  inSec = 0,
  outSec,
  audio = false,
  frameMode = 'cover',
  note,
}) => {
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

  const video = (
    <OffthreadVideo
      src={staticFile(`footage/${src}.mp4`)}
      startFrom={Math.round(inSec * fps)}
      endAt={outSec ? Math.round(outSec * fps) : undefined}
      muted={!audio}
      volume={audio ? 1 : 0}
      style={{width: '100%', height: '100%', objectFit: frameMode === 'band' ? 'contain' : 'cover'}}
    />
  );

  if (frameMode === 'band') {
    return (
      <AbsoluteFill style={{background: COLORS.bg}}>
        {video}
        {/* Marca discreta arriba para el look "producido". */}
        <div
          style={{
            position: 'absolute',
            top: 64,
            left: 0,
            right: 0,
            textAlign: 'center',
            fontFamily: FONTS.sans,
            fontWeight: 800,
            fontSize: 34,
            letterSpacing: 2,
            color: COLORS.inkDim,
          }}
        >
          {BRAND.product}
        </div>
      </AbsoluteFill>
    );
  }

  return <AbsoluteFill style={{background: COLORS.bg}}>{video}</AbsoluteFill>;
};
