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
    /** Cómo se anuncia la barra entera, no una de sus pestañas. */
    navegacion: "Secciones de Marea",
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
    walletShort: "Cartera",
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
    "materias-primas": "Materias primas",
    clima: "Clima",
    otros: "Otros",
  },

  /**
   * Cripto en vivo. Tuteado y sin jerga de trading: "paga 1.9×" se entiende en
   * cualquier mesa de Latam; "odds" y "payout" no.
   */
  vivo: {
    /** "vela de 5 min" — cuál es la ventana de la que se habla. */
    ventana: (minutos: number) => `vela de ${minutos} min`,
    /** Lo que queda para poder entrar. */
    restante: (reloj: string) => `cierra en ${reloj}`,
    cerrando: "cerrando",
    /** El ticker no tiene lectura fresca. Se dice; no se repite la última. */
    sinPrecio: "sin precio",
    paga: (multiplicador: string) => `paga ${multiplicador}`,
    /** Contra qué se compara el cierre de la vela. */
    strike: (precio: string) => `desde ${precio}`,
  },

  badges: {
    live: "LIVE",
    hot: "HOT",
    latam: "LATAM",
    resolved: "Resuelto",
    closingSoon: "Cierra pronto",
    closed: "Cerrado",
    /** Entre el cierre y el pago: ni vivo ni terminado. */
    settling: "Resolviendo",
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
    /** En la card, con los dos lados a la vista: "Sí · paga 1.8×". */
    pays: "paga",
    payoutHint: (multiplier: string, toWin: string) =>
      `Si aciertas, cobras ${toWin} (${multiplier}).`,
    poolTitle: "Cómo se reparte",
    poolBody: (si: string, no: string, fee: string) =>
      `Al Sí hay ${si} y al No ${no}. Quien acierta se reparte todo el pozo menos ${fee} de comisión. Marea no apuesta contra ti.`,
    /** El mismo reparto cuando la pregunta tiene más de dos respuestas. */
    poolBodyN: (reparto: string, fee: string) =>
      `${reparto}. Quien acierta se reparte todo el pozo menos ${fee} de comisión. Marea no apuesta contra ti.`,
    poolShare: (label: string, monto: string) => `A ${label} hay ${monto}`,
    /** Con N respuestas ya no es "tu lado": es cuál de todas. */
    chooseOutcome: "Elige tu respuesta",
    hereLabel: "Aquí",
    /** Personas dentro del mercado, no apuestas: veinte de una no son mercado. */
    participantes: (n: number) => (n === 1 ? "1 jugando" : `${n} jugando`),
    /** Cierre con fecha, no sólo "en 4 d": saber el día cambia la decisión. */
    cierraEl: (fecha: string) => `Cierra el ${fecha}`,
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
    /** Card: el pago de cada lado, debajo de su nombre. */
    pays2: (multiplier: string) => `paga ${multiplier}`,
    /** Card multi-resultado: lo que hay debajo de las tres que se enseñan. */
    respuestasMas: (n: number) => (n === 1 ? "+1 respuesta" : `+${n} respuestas`),
    /** Card en resolución: qué se está esperando, sin prometer cuándo. */
    esperandoFuente: "Esperando la fuente",
    /** Marcador de béisbol: la mitad de la entrada se dice con palabra. */
    entrada: (n: number, mitad: "alta" | "baja") =>
      `${mitad === "alta" ? "ALTA" : "BAJA"} ${n}ª`,
    outs: (n: number) => (n === 1 ? "1 out" : `${n} out`),
    /** Etiqueta accesible de cada pill: nombre, probabilidad y pago. */
    pillLabel: (label: string, probabilidad: string, multiplier: string) =>
      `${label}, ${probabilidad} %, paga ${multiplier}`,
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

  // la misma cosa se llamaba "cartera" en la pestaña y "wallet" en los botones.
  // Media traducción es peor que ninguna: obliga a deducir que son lo mismo
  wallet: {
    title: "Tu cartera",
    create: "Crear cartera",
    creating: "Creando…",
    connect: "Conectar cartera",
    connecting: "Conectando…",
    ready: "Tu cartera está lista",
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
    // al entrar no se está eligiendo nada: pedirle un mínimo a quien ya tiene
    // su contraseña se lee como si la suya no sirviera
    usuarioPlaceholderEntrar: "tu usuario",
    passwordPlaceholderEntrar: "tu contraseña",
    crearCta: "Crear cuenta y apostar",
    entrarCta: "Entrar",
    enviando: "Un segundo…",
    yaTengo: "Ya tengo cuenta",
    noTengo: "Quiero crear una cuenta",
    salir: "Cerrar sesión",
    sesionDe: (usuario: string) => `Tu cuenta: ${usuario}`,
    sinCuenta: "Estás explorando sin cuenta.",
    sinCuentaCta: "Crear cuenta",
    // el código se enseña una sola vez: si no lo guardas, la cuenta se pierde
    codigoTitulo: "Guarda este código",
    codigoCuerpo:
      "Es lo único que te devuelve la cuenta si olvidas tu contraseña. No lo volvemos a mostrar y no lo tenemos guardado: si lo pierdes, no hay forma de recuperarte.",
    codigoCopiar: "Copiar código",
    codigoCopiado: "Copiado",
    codigoListo: "Ya lo guardé",
    olvide: "Olvidé mi contraseña",
    recuperarTitulo: "Recupera tu cuenta",
    recuperarCuerpo: "Con tu usuario y el código que guardaste al crear la cuenta.",
    codigo: "Código de recuperación",
    codigoPlaceholder: "XXXX-XXXX-XXXX",
    passwordNueva: "Contraseña nueva",
    recuperarCta: "Recuperar mi cuenta",
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
    emptyCta: "Apostar en un mercado",
    loading: "Cargando tabla",
  },

  /** Sin conexión: lo que hay se sigue viendo, y se dice que está viejo. */
  frescura: {
    viejo: "Sin conexión. Esto es lo último que cargamos.",
    reintentar: "Reintentar",
  },

  /** El momento de cobrar: se entera al volver, no yendo a buscarlo. */
  liquidado: {
    title: "Cobraste",
    unaSola: (titulo: string) => `Resolvió “${titulo}”.`,
    varias: (n: number) => `Resolvieron ${n} de tus mercados.`,
    total: "Se acreditó a tu saldo",
    comoSeSupo: "Cómo se supo",
    ver: "Ver portafolio",
    cerrar: "Entendido",
  },

  postTrade: {
    title: "Listo, tu posición está abierta",
    body: (side: string, amount: string, title: string) =>
      `${side} · ${amount} en “${title}”.`,
    /** Lo que cobra si acierta: es la cifra protagonista de la confirmación. */
    cobras: "Cobras si aciertas",
    entraste: (side: string, prob: string) => `${side} a ${prob}%`,
    pusiste: (amount: string) => `Pusiste ${amount}`,
    compartir: "Contarle a alguien",
    compartido: "Liga copiada",
    compartirTexto: (side: string, title: string) =>
      `Aposté ${side} en “${title}”. ¿Tú qué dices?`,
    goPortfolio: "Ver portafolio",
    keepExploring: "Seguir explorando",
  },

  onboarding: {
    p1Title: "Predice. Opera. Con edge.",
    p1Body:
      "Mercados de predicción en español. Te mostramos la probabilidad del mercado y la nuestra, lado a lado.",
    p1Cta: "Empezar",
    /** Encima del mercado de muestra: dice qué se está mirando. */
    p1Muestra: "Así se ve un mercado",
    p1VerTodos: "Ver los mercados",
    p2Title: "Tu cartera, en un tap",
    p2Body:
      "Creamos una cartera para ti. Sin trámites, sin documentos, sin frases que memorizar.",
    p2Primary: "Crear cartera",
    p2Secondary: "Conectar cartera",
    p3Title: "Tu cartera está lista",
    p3Body: "Puedes explorar todo sin depositar. Deposita cuando quieras operar.",
    p3Primary: "Depositar",
    p3Secondary: "Explorar mercados",
    skip: "Explorar primero",
  },

  logro: {
    titulo: "Tu tarjeta",
    cuerpo: "Tu precisión y tu racha, en una imagen para mandar al grupo.",
    cta: "Compartir mi tarjeta",
    copiada: "Liga copiada",
    texto: "Así voy en Marea. ¿Le atinas más que yo?",
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
