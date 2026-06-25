/** Real brand handles & links. Keyword for DM is "FQ". */
export const LINKS = {
  telegramDM: 'https://t.me/RASDG05',
  telegramHandle: '@RASDG05',
  instagram: 'https://instagram.com/diego_gallegosd',
  instagramHandle: '@diego_gallegosd',
  bot: 'https://t.me/rasdg_quantum_signals_bot',
  botHandle: '@rasdg_quantum_signals_bot',
} as const

/**
 * Intro video. Inject at build time via Vite env `VITE_VIDEO_EMBED_URL`
 * (a YouTube/Vimeo *embed* URL, e.g. https://www.youtube.com/embed/XXXX).
 * If empty, a tasteful placeholder is shown instead.
 */
export const VIDEO_EMBED_URL: string = import.meta.env.VITE_VIDEO_EMBED_URL ?? ''
