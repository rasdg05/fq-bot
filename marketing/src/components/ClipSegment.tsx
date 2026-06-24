import React from 'react';
import {AbsoluteFill, OffthreadVideo, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {BRAND, COLORS, FONTS, FOOTAGE_AVAILABLE, GLYPHS} from '../brand/tokens';

export type FrameMode = 'cover' | 'band';

/** Overlay (B-roll) que aparece encima los primeros frames, mudo, con fade out. */
export type Overlay = {src: string; inSec?: number; outSec?: number; frames: number};

export type ClipProps = {
  src: string;
  inSec?: number;
  outSec?: number;
  audio?: boolean;
  frameMode?: FrameMode;
  /** B-roll mudo encima al inicio (la voz del clip base sigue sonando). */
  overlay?: Overlay;
  note?: string;
};

const OverlayClip: React.FC<{overlay: Overlay}> = ({overlay}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const opacity = interpolate(frame, [overlay.frames - 10, overlay.frames], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return (
    <AbsoluteFill style={{opacity}}>
      <OffthreadVideo
        src={staticFile(`footage/${overlay.src}.mp4`)}
        startFrom={Math.round((overlay.inSec ?? 0) * fps)}
        endAt={overlay.outSec ? Math.round(overlay.outSec * fps) : undefined}
        muted
        volume={0}
        style={{width: '100%', height: '100%', objectFit: 'cover'}}
      />
    </AbsoluteFill>
  );
};

export const ClipSegment: React.FC<ClipProps> = ({
  src,
  inSec = 0,
  outSec,
  audio = false,
  frameMode = 'cover',
  overlay,
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

  const overlayEl = overlay ? (
    <Sequence durationInFrames={overlay.frames}>
      <OverlayClip overlay={overlay} />
    </Sequence>
  ) : null;

  if (frameMode === 'band') {
    return (
      <AbsoluteFill style={{background: COLORS.bg}}>
        {video}
        {overlayEl}
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

  return (
    <AbsoluteFill style={{background: COLORS.bg}}>
      {video}
      {overlayEl}
    </AbsoluteFill>
  );
};
