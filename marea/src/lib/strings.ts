/**
 * Todo el texto visible de la app vive aquí (R-007). Español Latam.
 * Copy cerrado por VOICE.md: cambiarlo requiere pasar por AUDIT.
 */
export const S = {
  brand: {
    name: "Marea",
    tagline: "Predice. Opera. Con edge.",
  },

  tabs: {
    markets: "Mercados",
    search: "Buscar",
    portfolio: "Portafolio",
    wallet: "Cartera",
    profile: "Perfil",
  },

  header: {
    balance: "Saldo",
    deposit: "Depositar",
    noFunds: "Sin saldo",
    walletShort: "Wallet",
  },

  feed: {
    hotNow: "Hot ahora",
    allCategories: "Todos",
    sectionAll: "Todos los mercados",
    empty: "No hay mercados calientes en este momento. Vuelve en un rato.",
    emptyCta: "Ver todos los mercados",
    emptyFiltered: "No hay mercados en esta categoría por ahora.",
    retry: "Reintentar",
    loading: "Cargando mercados",
  },

  categories: {
    cripto: "Cripto",
    economia: "Economía",
    deportes: "Deportes",
    politica: "Política",
    cultura: "Cultura",
    otros: "Otros",
  },

  badges: {
    live: "LIVE",
    hot: "HOT",
    latam: "LATAM",
    resolved: "Resuelto",
    closingSoon: "Cierra pronto",
  },

  market: {
    probability: "Probabilidad",
    marketProbability: "Mercado",
    mareaProbability: "Marea",
    edge: "Edge",
    /** Card: "Marea +7%" */
    edgeCard: (pp: string) => `Marea ${pp}%`,
    /** Detalle: "Mercado 62% · Marea 69% · Edge +7%" */
    edgeDetail: (market: string, marea: string, edge: string) =>
      `Mercado ${market}% · Marea ${marea}% · Edge ${edge}%`,
    edgeBasis: "Base de la lectura",
    venueNotice: (venue: string) => `Este mercado vive en ${venue}.`,
    edgeExplainer:
      "Edge es la diferencia entre la probabilidad del mercado y la nuestra. Solo la mostramos cuando pasa de 4 puntos.",
    volume: "Volumen",
    closes: "Cierra",
    resolution: "Cómo se resuelve",
    yes: "Sí",
    no: "No",
    chooseSide: "Elige tu lado",
    amount: "Monto",
    tradeCta: "Operar",
    tradePreparing: "Preparando…",
    tradeDisabledReason: "Este mercado ya cerró.",
    aggregatedNotice:
      "Tu operación se completa en el mercado con más liquidez. Marea no es tu contraparte y no cobra spread escondido.",
    maxLoss: "Lo máximo que puedes perder es lo que pones.",
    openDetail: "Ver mercado",
  },

  wallet: {
    title: "Tu cartera",
    create: "Crear wallet",
    creating: "Creando…",
    connect: "Conectar wallet",
    connecting: "Conectando…",
    ready: "Tu wallet está lista",
    readyBody:
      "Ya puedes explorar todos los mercados. Deposita solo cuando quieras operar.",
    address: "Dirección",
    chain: "Red",
    balanceZero: "Aún no tienes saldo",
    balanceZeroBody: "Explora los mercados sin depositar nada.",
    copy: "Copiar",
    copied: "Copiado",
  },

  deposit: {
    title: "Depositar",
    subtitle: "Elige cómo quieres fondear tu cartera.",
    card: "Con tarjeta o transferencia local",
    cardBody: "Compra USDC en tu moneda. Llega en minutos.",
    crypto: "Transferir cripto",
    cryptoBody: "Envía USDC a tu dirección de Marea desde cualquier exchange.",
    close: "Cerrar",
    continue: "Continuar",
    starting: "Abriendo…",
    providerDown: "Proveedor no disponible",
    startedOnramp:
      "Te vamos a llevar con nuestro proveedor de pago para comprar USDC.",
    startedTransfer: "Envía USDC a tu dirección de Marea en la red Polygon.",
    minNote: "Sin monto mínimo. Empieza con lo que quieras.",
    blockedTitle: "Todavía no abrimos depósitos donde estás",
    keepExploring: "Seguir explorando",
  },

  portfolio: {
    title: "Portafolio",
    empty: "Todavía no tienes posiciones.",
    emptyBody: "Cuando operes un mercado, lo vas a ver aquí.",
    emptyCta: "Ver mercados",
    open: "Abiertas",
    settled: "Cerradas",
    pnl: "Resultado",
    invested: "Invertido",
    side: "Lado",
    loading: "Cargando portafolio",
  },

  postTrade: {
    title: "Listo, tu posición está abierta",
    body: (side: string, amount: string, title: string) =>
      `${side} · ${amount} en “${title}”.`,
    goPortfolio: "Ver portafolio",
    keepExploring: "Seguir explorando",
  },

  onboarding: {
    p1Title: "Predice. Opera. Con edge.",
    p1Body:
      "Mercados de predicción en español. Te mostramos la probabilidad del mercado y la nuestra, lado a lado.",
    p1Cta: "Empezar",
    p2Title: "Tu cartera, en un tap",
    p2Body:
      "Creamos una wallet para ti. Sin trámites, sin documentos, sin frases que memorizar.",
    p2Primary: "Crear wallet",
    p2Secondary: "Conectar wallet",
    p3Title: "Tu wallet está lista",
    p3Body: "Puedes explorar todo sin depositar. Deposita cuando quieras operar.",
    p3Primary: "Depositar",
    p3Secondary: "Explorar mercados",
    skip: "Explorar primero",
  },

  profile: {
    title: "Perfil",
    theme: "Tema",
    themeDark: "Oscuro",
    themeLight: "Claro",
    responsible: "Juego responsable",
    responsibleBody:
      "Lo máximo que puedes perder es lo que pones. Nunca hay crédito ni apalancamiento. Si sientes que se te va de las manos, puedes pausar tu cuenta.",
    pause: "Pausar mi cuenta",
    honesty: "Cómo funciona Marea",
    honestyBody:
      "Cobramos una comisión por operación. No somos tu contraparte: no ganamos cuando pierdes.",
    version: "Versión",
  },

  search: {
    title: "Buscar",
    placeholder: "Busca un mercado…",
    empty: "No encontramos mercados con eso.",
    emptyBody: "Prueba con otra palabra o revisa las categorías.",
    byCategory: "Por categoría",
    results: "Resultados",
  },

  common: {
    retry: "Reintentar",
    back: "Volver",
    close: "Cerrar",
    cancel: "Cancelar",
    loading: "Cargando",
    error: "Algo salió mal",
  },
} as const;

export type Strings = typeof S;
