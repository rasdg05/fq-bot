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
    closed: "Cerrado",
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
    pot: "Pozo",
    closes: "Cierra",
    resolution: "Cómo se resuelve",
    resolvedAs: (lado: string) => `Resolvió: ${lado}`,
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
    payout: "Paga",
    payoutHint: (multiplier: string, toWin: string) =>
      `Si aciertas, cobras ${toWin} (${multiplier}).`,
    poolTitle: "Cómo se reparte",
    poolBody: (si: string, no: string, fee: string) =>
      `Al Sí hay ${si} y al No ${no}. Quien acierta se reparte todo el pozo menos ${fee} de comisión. Marea no apuesta contra ti.`,
    hereLabel: "Aquí",
    referenceLabel: (venue: string) => venue,
    edgeCardWith: (label: string, pp: string) => `${label} ${pp}%`,
    edgeDetailWith: (here: string, label: string, there: string, edge: string) =>
      `Aquí ${here}% · ${label} ${there}% · Edge ${edge}%`,
    compartir: "Compartir",
    compartido: "Liga copiada",
    compartirTexto: (titulo: string, probabilidad: string) =>
      `${titulo}\n\nEl mercado dice ${probabilidad} que sí. ¿Tú qué dices?`,
    betCta: "Apostar",
    closedForBets: "Este mercado ya cerró.",
  },

  points: {
    title: "Tus puntos",
    disclaimer:
      "Estás jugando con puntos, no con dinero. No se cambian por efectivo ni por cripto.",
    disclaimerShort: "Puntos, no dinero.",
    why: "Por qué puntos primero",
    whyBody:
      "Antes de que alguien arriesgue un peso queremos saber si los mercados están bien hechos y si la resolución es transparente. Cuando eso esté probado y el marco legal resuelto, avisamos.",
    topUp: "Recargar puntos",
    topUpDone: "Puntos recargados",
    topUpUnavailable: "Ya recargaste hoy. Vuelve mañana.",
    welcome: (amount: string) => `Te dimos ${amount} para empezar.`,
    balanceZero: "Te quedaste sin puntos",
    balanceZeroBody: "Recarga y sigue apostando. Explorar no cuesta nada.",
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
    toWin: "Si aciertas",
    atRisk: "Arriesgas",
    invested: "Invertido",
    side: "Lado",
    loading: "Cargando portafolio",
    won: "Ganaste",
    lost: "Perdiste",
    refunded: "Devuelto",
    paid: "Pagado",
    // el pago va con la lectura que lo justifica: cobrar no es un acto de fe
    evidence: "Cómo se resolvió",
  },

  cuenta: {
    crearTitulo: "Crea tu cuenta",
    crearCuerpo:
      "Para que tus apuestas y tus puntos sigan aquí cuando vuelvas. Dos campos, sin correo y sin esperar nada.",
    entrarTitulo: "Entra a tu cuenta",
    entrarCuerpo: "Con tu usuario y tu contraseña recuperas tu saldo y tus posiciones.",
    usuario: "Usuario",
    usuarioPlaceholder: "como te van a ver los demás",
    password: "Contraseña",
    passwordPlaceholder: "mínimo 8 caracteres",
    crearCta: "Crear cuenta y apostar",
    entrarCta: "Entrar",
    enviando: "Un segundo…",
    yaTengo: "Ya tengo cuenta",
    noTengo: "Quiero crear una cuenta",
    salir: "Cerrar sesión",
    sesionDe: (usuario: string) => `Tu cuenta: ${usuario}`,
    sinCuenta: "Estás explorando sin cuenta.",
    sinCuentaCta: "Crear cuenta",
  },

  tabla: {
    title: "Tabla",
    subtitle: "Quién le atina más, no quién apuesta más.",
    empty: "Todavía nadie tiene mercados resueltos.",
    emptyBody: "En cuanto se liquide el primero, aquí aparece quién le atinó.",
    usuario: "Jugador",
    puntos: "Puntos",
    precision: "Precisión",
    racha: "Racha",
    tuPosicion: (posicion: number) => `Vas en el lugar ${posicion}`,
    fueraDeTabla: "Aún no tienes mercados resueltos.",
    loading: "Cargando tabla",
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
