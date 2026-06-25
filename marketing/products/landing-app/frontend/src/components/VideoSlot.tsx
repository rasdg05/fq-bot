import { motion } from 'framer-motion'
import { VIDEO_EMBED_URL } from '../lib/constants'

/**
 * Responsive 16:9 intro video slot.
 * - If VIDEO_EMBED_URL is set -> render a YouTube/Vimeo iframe.
 * - Otherwise -> tasteful placeholder with a play button + note.
 */
export default function VideoSlot() {
  return (
    <div className="mx-auto mb-2 mt-[30px] max-w-[680px]">
      <div className="relative aspect-video overflow-hidden rounded-2xl border border-hairline">
        {VIDEO_EMBED_URL ? (
          <iframe
            className="absolute inset-0 h-full w-full"
            src={VIDEO_EMBED_URL}
            title="Video de introducción"
            frameBorder={0}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowFullScreen
          />
        ) : (
          <div
            className="flex h-full w-full items-center justify-center"
            style={{ background: 'linear-gradient(160deg,#10151d,#0a0d12)' }}
          >
            <motion.div
              whileHover={{ scale: 1.06 }}
              whileTap={{ scale: 0.96 }}
              className="flex h-[74px] w-[74px] items-center justify-center rounded-full bg-accent shadow-glow"
            >
              {/* Play triangle */}
              <span
                className="ml-1.5 block"
                style={{
                  width: 0,
                  height: 0,
                  borderStyle: 'solid',
                  borderWidth: '13px 0 13px 22px',
                  borderColor: 'transparent transparent transparent #07140f',
                }}
              />
            </motion.div>
          </div>
        )}
      </div>
      {!VIDEO_EMBED_URL && (
        <div className="mt-2.5 text-center text-xs text-faint">
          ▲ Aquí va tu video de introducción (1–2 min)
        </div>
      )}
    </div>
  )
}
