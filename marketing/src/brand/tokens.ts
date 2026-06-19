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
  bg: '#0A0C10',
  panel: '#10141B',
  panelHi: '#161B24',
  hairline: '#222A35',
  ink: '#E7EAEE',
  inkDim: '#8A93A2',
  inkFaint: '#5A626E',
  accent: '#C8CDD6', // acento vertical / wordmark (frio, sobrio)
  long: '#34D399', // ▲
  short: '#F87171', // ▼
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
 * Cierre orientado a COMUNIDAD / marca personal (no a oferta).
 * El activo es la atencion: primero tribu, despues el resto.
 */
export const COMMUNITY = {
  join: 'Unete a la comunidad',
  line: 'Trading con sistema, no con ego',
  note: 'Estamos abriendo cupos',
} as const;

/** Destinos de CTA. Rellena con tus datos reales. */
export const CTA_CONFIG = {
  botUsername: 'TU_BOT', // sin @ — ver FQ_VIP_BOT_USERNAME en .env
  botDeepLink: 'https://t.me/TU_BOT?start=ads',
  instagram: 'diego_gallegosd',
  // Hub link-in-bio (Linkme): rellena con tu URL real. Vacio = no se muestra.
  linkme: '',
} as const;
