/**
 * Identidad visual FQ — espejo de branding.py.
 * Direccion: "Terminal / mesa de liquidez institucional".
 * Sobrio, sin emoji, hairline + acento vertical, tipografia con aire.
 */

export const BRAND = {
  product: 'FQ',
  productLong: 'Fibonacci Cuantico',
  // Motor multi-simbolo: no se ancla a un solo par.
  symbols: ['SOL/USDT', 'BTC/USDT', 'ETH/USDT'],
  desk: 'Mesa de liquidez',
  tagline: 'Mesa de liquidez institucional · multi-simbolo',
  promise: 'Cuando hay ventaja, ejecuta. Cuando no, espera.',
  disclaimer: 'Rendimientos pasados no garantizan resultados futuros. No es asesoria financiera.',
} as const;

/** English string set (parallel EN campaign). Same compliance, same lane. */
export const BRAND_EN = {
  productLong: 'Fibonacci Quantum',
  promise: 'When there is an edge, it executes. When there is not, it waits.',
  disclaimer: 'Past performance does not guarantee future results. Not financial advice.',
  desk: 'Liquidity desk',
  online: 'multi-symbol · online',
} as const;

export const COMMUNITY_EN = {
  join: 'Get the FREE guide',
  line: '5 rules to trade with a system',
  note: 'Free · no spam',
} as const;

/** CTA chip labels in English (mirror of the inline Spanish in CTA.tsx). */
export const CTA_TEXT_EN = {
  bot: 'Open the bot',
  telegram: 'Text me on Telegram',
  telegramSub: 'send the word',
  webLabel: 'Download it free',
  webValue: 'Tap "Learn more" ↓',
  follow: 'Follow me',
  linkInBio: 'link in bio',
  signal: {entry: 'Entry defined', stop: 'Stop defined', target: 'Target by structure'},
} as const;

/** Glifos hairline (branding.py GLYPHS). */
export const GLYPHS = {
  rule: '─'.repeat(30), // ─
  title: '│', // │
  bulletAct: '›', // ›
  bulletChk: '·', // ·
  long: '▲', // ▲
  short: '▼', // ▼
} as const;

export const COLORS = {
  // Marca curada FQ (espejo del terminal / avatar / banner): oro + Solana sobre negro.
  bg: '#060806',
  panel: '#0E1210',
  panelHi: '#141915',
  hairline: '#2B2718', // hairline con tinte dorado
  ink: '#F4F2EA',
  inkDim: '#B9B6A6',
  inkFaint: '#6E6C60',
  accent: '#D4AF37', // ORO — acento vertical / wordmark (marca curada)
  sol1: '#9945FF', // Solana violeta (gradiente/hairline vivo)
  sol2: '#14F195', // Solana menta
  long: '#21C96B', // ▲
  short: '#E05E5E', // ▼
} as const;

export const FONTS = {
  // Stacks del sistema: render fiable sin depender de red.
  mono: '"SF Mono","JetBrains Mono",ui-monospace,Menlo,Consolas,monospace',
  sans: 'Inter,"Helvetica Neue",system-ui,-apple-system,sans-serif',
} as const;

export const VIDEO = {
  width: 1080,
  height: 1920,
  fps: 30,
} as const;

/**
 * Cuando metas tu footage real (marketing/public/footage/<nombre>.mp4) y lo
 * cortes con `npm run ingest`, pon esto en true. Mientras sea false los
 * clips se renderizan como "slate" de marca, asi el proyecto corre sin video.
 */
export const FOOTAGE_AVAILABLE = true;

/**
 * Cama musical (esquema mixto). Pon tu pista con licencia en
 * public/audio/music.mp3. Si no quieres musica, enabled:false.
 */
export const MUSIC = {
  enabled: true,
  file: 'audio/music.mp3',
  volume: 0.1,
} as const;

/**
 * Cierre orientado a la OFERTA: guía gratis (lead magnet).
 * Un regalo específico convierte mejor que "sígueme".
 */
export const COMMUNITY = {
  join: 'Descarga la guía GRATIS',
  line: '5 reglas para operar con sistema',
  note: 'Gratis · sin spam',
} as const;

/** Destinos de CTA. Rellena con tus datos reales. */
export const CTA_CONFIG = {
  botUsername: 'rasdg_quantum_signals_bot',
  botDeepLink: 'https://t.me/rasdg_quantum_signals_bot?start=ads',
  instagram: 'diego_gallegosd',
  // Hub link-in-bio (Linkme): rellena con tu URL real. Vacio = no se muestra.
  linkme: '',
  // DM de Telegram (anuncio que manda a tu chat directo para cerrar tu la venta).
  telegramUser: 'RASDG05',
  telegramLink: 'https://t.me/RASDG05',
  keyword: 'FQ',
} as const;
