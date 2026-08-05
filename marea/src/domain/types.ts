import type { Outcome, OutcomeId, Pool } from "./parimutuel";

/**
 * Contratos de dominio. Cerrados por ARCH: los adapters se adaptan a estos
 * tipos, nunca al revés. La UI no conoce ninguna otra forma de dato.
 */

/**
 * `settling` es el hueco que faltaba: entre que el mercado cierra y que la
 * fuente entrega el dato, la tarjeta decía "Cerrado" como si ya hubiera
 * terminado. Vivo, cerrado y resolviendo son tres cosas distintas y cada una
 * tiene su palabra.
 */
export type MarketStatus =
  | "open"
  | "closing_soon"
  | "live"
  | "settling"
  | "resolved";

/**
 * Marcador en vivo, estructurado por deporte. Es un tipo aparte de `marcador`
 * —que sigue siendo el resultado final de fútbol— porque un set de tenis y una
 * entrada de béisbol no caben en `{ local, visitante }`, y forzarlos ahí era
 * lo que dejaba a las tarjetas en vivo sin decir nada del evento.
 *
 * `equipos` viaja como par para que la tarjeta no tenga que adivinar el orden:
 * el primero es el local, o quien saca, según el deporte.
 */
export type MarcadorVivo =
  | {
      deporte: "futbol";
      equipos: [string, string];
      goles: [number, number];
      /** `72'`, tal como se muestra. */
      minuto?: string;
    }
  | {
      deporte: "tenis";
      jugadores: [string, string];
      /** Un par por set jugado, en orden. El último es el set en curso. */
      sets: [number, number][];
      /** Índice de quien saca, para el punto de la fila de marcador. */
      saque?: 0 | 1;
      /** El game en curso, `40-30`. Vive en un badge, no en la fila. */
      game?: string;
    }
  | {
      deporte: "beisbol";
      equipos: [string, string];
      carreras: [number, number];
      entrada: number;
      mitad: "alta" | "baja";
      outs: number;
      /** Estado de bases en palabras: `1ª y 3ª`, `Bases limpias`. */
      bases?: string;
    };

/**
 * Lo último que pasó en el partido. Gramática cerrada —`<sustantivo> hace
 * <n> min`— porque es el segmento del pie que más se mueve y el que primero
 * rompe la línea. El vocabulario está acotado en `lib/format.ts`.
 */
export interface EventoReciente {
  tipo:
    | "quiebre"
    | "set"
    | "gol"
    | "roja"
    | "penal"
    | "carrera"
    | "jonron"
    | "ponche"
    | "cambio_pitcher";
  /** Minutos desde que ocurrió. A los 10 deja de ser reciente. */
  hace: number;
}

export type MarketCategory =
  | "cripto"
  | "economia"
  | "deportes"
  | "politica"
  | "cultura"
  /**
   * Las dos que todavía no tienen catálogo. Están en el tipo —y no sólo en una
   * nota— para que su color, su glifo y su palabra existan antes que su primer
   * mercado: el día que lleguen no se improvisa nada, y mientras tanto el
   * compilador señala cualquier mapa por categoría al que le falten.
   * No salen como pestaña: una que filtra a cero mercados es un callejón.
   */
  | "materias-primas"
  | "clima"
  /** Sin señal clara para clasificar. Preferimos decirlo a inventar categoría. */
  | "otros";

/**
 * Una vela viva, tal como la ve la interfaz. Todo lo que hace falta para pintar
 * la card sin que la UI calcule nada de dominio: el reloj, el strike, el precio
 * de ahora y de dónde salió.
 */
export interface LiveCandle {
  /** Par tal como lo cotiza la fuente: `BTC/USD`. */
  par: string;
  /** Cómo se le dice a la gente: `Bitcoin`. */
  activo: string;
  /** Minutos de la vela: 5 o 15. */
  intervalo: number;
  /** Apertura de la vela, ISO. */
  abreAt: string;
  /** Cierre de la vela — el momento que se liquida, ISO. */
  cierraAt: string;
  /** Cuándo dejan de aceptarse apuestas, ISO. Siempre antes de `cierraAt`. */
  bloqueaAt: string;
  /** Precio de referencia. `Arriba` exige cierre estrictamente mayor. */
  strike: number;
  /** Último precio leído. Ausente = el ticker no tiene lectura fresca. */
  spot?: number;
  /** Variación del spot contra el strike, en puntos porcentuales. */
  deltaPp?: number;
  /** Quién dio ese precio: el motor propio o el feed público (R-022). */
  fuente?: string;
  /** Cuándo se leyó ese precio, ISO. Es lo que dice si está fresco. */
  spotAt?: string;
}

/**
 * El pulso de una vela: lo único que cambia mientras corre. Viaja aparte del
 * mercado y varias veces por minuto, así que lleva lo mínimo — repetir el
 * título y el criterio de resolución en cada latido sería gastar la red de la
 * gente en algo que no se movió (R-047).
 */
export interface PulsoVivo {
  id: string;
  strike: number;
  spot?: number;
  deltaPp?: number;
  fuente?: string;
  spotAt?: string;
  bloqueaAt: string;
  cierraAt: string;
  /** Probabilidad de cada resultado, por id. Suman 1. */
  probabilidades: Record<string, number>;
  /** Cuánto paga cada resultado por unidad apostada, por id. */
  multiplicadores: Record<string, number>;
  pozo: number;
  jugando: number;
}

export interface Market {
  id: string;
  title: string;
  /**
   * El título como se pinta en la tarjeta: afirmativo, sin signo de
   * interrogación y de 42 caracteres para arriba se corta. Existe porque el
   * título completo cae en dos líneas y esas dos líneas eran 19 px de tarjeta
   * — el recorte más caro del rediseño. Sin él, la tarjeta usa `title`.
   */
  shortTitle?: string;
  /** Probabilidad del mercado, 0..1. Nodo tipográfico dominante (R-004). */
  probability: number;
  /** Volumen operado, en USD. */
  volume: number;
  status: MarketStatus;
  category: MarketCategory;
  /**
   * Edge en puntos porcentuales, ya filtrado por el umbral de dominio
   * (`>= EDGE_MIN_PP`). `null` significa "no hay edge que mostrar" (R-001).
   * Nunca lo calcula la UI: lo entrega el dominio vía `withEdge()`.
   */
  edge: number | null;
  /** Criterio de resolución, en una frase clara. Se muestra antes de operar. */
  resolution_summary: string;
  /** Probabilidad estimada por Marea, 0..1. Ausente => no hay lectura propia. */
  mareaProbability?: number;
  /** El porqué de esa lectura, mostrable. Sin base no se muestra Edge (R-019). */
  mareaBasis?: string;
  /**
   * Cómo se llama la lectura frente a la que se compara el precio. En mercados
   * propios la lectura viene de una casa global, no de un modelo nuestro, y
   * llamarla "Marea" sería mentir (R-027).
   */
  edgeLabel?: string;
  /** Etiqueta del precio propio en el detalle: "Mercado" o "Aquí". */
  priceLabel?: string;
  /** Estado del pozo, cuando el mercado es parimutuel propio. */
  pool?: Pool;
  /**
   * Los resultados posibles, en el orden en que los declaró el mercado. El
   * binario los trae también (`si`/`no`): así la UI no tiene dos caminos, sólo
   * dos formas de pintar la misma lista (R-063).
   */
  outcomes?: Outcome[];
  /**
   * De qué resultado habla `probability` cuando hay más de dos. En binario
   * sobra —siempre es el Sí—; con N respuestas, un porcentaje sin nombre es un
   * número que no dice nada.
   */
  leadLabel?: string;
  /**
   * Cuánta gente distinta apostó. Personas, no apuestas: veinte apuestas de
   * una sola persona no son un mercado (R-059).
   */
  participantes?: number;
  /**
   * Los dos equipos, cuando el mercado es de futbol. El escudo lo sirve la
   * misma fuente que resuelve el mercado, así que no se cita a nadie que no se
   * lea (R-046).
   */
  equipos?: { nombre: string; escudo?: string }[];
  /** Marcador, si el partido está en juego o ya terminó. */
  marcador?: { local: number; visitante: number; estado: string };
  /** Marcador estructurado del evento en curso. Sin esto no hay badge LIVE. */
  marcadorVivo?: MarcadorVivo;
  /** Lo último que pasó, para el pie de la tarjeta en vivo. */
  eventoReciente?: EventoReciente;
  /** Dónde se completa la operación cuando la ejecución es agregada. */
  venue?: { id: string; label: string; url?: string };
  /** Resultado ya leído de la fuente, cuando el mercado resolvió. */
  outcome?: PositionSide;
  /** Qué se leyó exactamente para resolver. Auditable por el usuario. */
  settlementEvidence?: string;
  /**
   * Estado de la vela, cuando el mercado es de cripto en vivo. Su presencia es
   * lo que convierte la card en una card viva: la UI no adivina el modo por la
   * categoría ni por el título.
   */
  live?: LiveCandle;
  /** Marca de tracción para el badge HOT. */
  hot?: boolean;
  /** Región del mercado, para el badge LATAM. */
  region?: "latam" | "global";
  /** País concreto. En un producto todo-Latam informa más que "LATAM". */
  country?: string;
  closesAt?: string;
}

/**
 * El lado de una posición es el id del resultado elegido. Con dos resultados
 * son `si` y `no`; con siete, los siete ids del mercado.
 */
export type PositionSide = OutcomeId;
export type PositionStatus = "open" | "won" | "lost" | "settled";

export interface Position {
  id: string;
  market_id: string;
  side: PositionSide;
  /**
   * El texto del resultado elegido. Sin esto, una posición en un mercado de
   * siete candidatos diría "Sí", que no es lo que apostó nadie.
   */
  sideLabel?: string;
  /** Tamaño en USD. */
  size: number;
  /** Precio de entrada, 0..1. */
  entry_price: number;
  /**
   * Resultado realizado. En parimutuel se queda en cero hasta que el mercado
   * resuelve: no hay marca a mercado porque no puedes salirte antes (R-029).
   */
  pnl: number;
  status: PositionStatus;
  marketTitle?: string;
  /** Lo que se cobra si el lado acierta, con el pozo de ahora. */
  toWin?: number;
  /** Cuánto paga cada unidad, con el pozo de ahora. */
  multiplier?: number;
  /** Lo efectivamente pagado al resolver. Sólo existe con el mercado liquidado. */
  payout?: number;
  /** Qué se leyó para resolver, para que el pago no sea un acto de fe. */
  evidence?: string;
}

export interface Wallet {
  address: string;
  /** Saldo disponible en USD. */
  balance: number;
  chain: string;
  /** Cómo llegó la wallet al usuario: creada por Marea o conectada por él. */
  origin: "embedded" | "connected";
}

export type AppErrorCode =
  | "E_WALLET_CREATE_FAILED"
  | "E_WALLET_CONNECT_FAILED"
  | "E_BALANCE_FETCH_FAILED"
  | "E_DEPOSIT_INIT_FAILED"
  | "E_DEPOSIT_PROVIDER_UNAVAILABLE"
  | "E_MARKETS_FETCH_FAILED"
  | "E_MARKET_DETAIL_FAILED"
  | "E_PORTFOLIO_FETCH_FAILED"
  | "E_TRADE_INIT_FAILED"
  | "E_NETWORK"
  | "E_UNKNOWN";

export interface AppError {
  code: AppErrorCode;
  /** Mensaje mostrable al usuario, español Latam. Nunca un stack trace (R-008). */
  user_message_es: string;
  retryable: boolean;
  context?: Record<string, unknown>;
}
